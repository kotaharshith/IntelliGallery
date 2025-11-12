import os
import sqlite3
import json
import easyocr
import numpy as np
import Levenshtein
from flask import Flask, request, jsonify, send_from_directory, g
from flask_cors import CORS
from PIL import Image
import io


UPLOAD_FOLDER = 'uploads'
DATABASE = 'gallery.db'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}


app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
CORS(app) 

print("Loading EasyOCR model... This may take a moment.")
reader = easyocr.Reader(['en']) 
print("EasyOCR model loaded successfully.")


def get_db():
    """Connects to the SQLite database."""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    """Closes the database connection at the end of the request."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    """Initializes the database schema."""
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            display_name TEXT NOT NULL,
            internal_filename TEXT NOT NULL UNIQUE, 
            full_text TEXT,
            ocr_data_json TEXT
        )
        ''')
        db.commit()
        print("Database initialized.")

def allowed_file(filename):
    """Checks if the file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def is_fuzzy_match(word, term):
    """
    Checks if a word is a 'close enough' match OR a substring match.
    e.g., term="time" matches word="time table" (substring)
    e.g., term="invoice" matches word="invo1ce" (fuzzy)
    """
    word_lower = word.lower()
    term_lower = term.lower()
    
    if term_lower in word_lower:
        return True
        
    distance = Levenshtein.distance(word_lower, term_lower)
    
    if len(term_lower) <= 5 and distance <= 1:
        return True
    if len(term_lower) > 5 and len(term_lower)<10 and distance <= 2:
        return True
    if len(term_lower) >=10 and distance <= 3:
        return True
    return False

def process_and_save_image(file_storage, display_name, internal_filename):
    """Helper function to run OCR and save data. Avoids code duplication."""
    
    img_bytes_io = io.BytesIO()
    file_storage.save(img_bytes_io)
    img_bytes_io.seek(0)

    try:
        img_np = np.array(Image.open(img_bytes_io))
    except Exception as e:
        return {"error": f"Failed to read image file: {str(e)}"}, 400
    
    img_bytes_io.seek(0)
    
    print(f"Running EasyOCR on {display_name} (as {internal_filename})...")
    try:
        ocr_results = reader.readtext(img_np, detail=1)
        print("OCR complete.")
    except Exception as e:
         return {"error": f"EasyOCR failed to process image: {str(e)}"}, 500

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], internal_filename)
    with open(filepath, 'wb') as f:
        f.write(img_bytes_io.read())
    
    full_text = " ".join([result[1] for result in ocr_results])
    
    words_data = []
    for (bbox, text, conf) in ocr_results:
        tl = bbox[0]
        br = bbox[2]
        x = int(tl[0])
        y = int(tl[1])
        w = int(br[0] - tl[0])
        h = int(br[1] - tl[1])
        words_data.append({
            "text": text.lower(),
            "bbox": [x, y, w, h]
        })
    
    return {
        "full_text": full_text.lower(),
        "ocr_data_json": json.dumps(words_data)
    }, 200 # 200 is a generic "OK"



@app.route('/upload', methods=['POST'])
def upload_image():
    """
    Receives an image.
    - If it's a new filename, it saves it.
    - If it's a duplicate, it returns 409 Conflict.
    - If called with action=new_copy, it saves with a unique ID.
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
        
    if not (file and allowed_file(file.filename)):
        return jsonify({"error": "File type not allowed"}), 400

    display_name = file.filename 
    action = request.args.get('action')

    if action == 'new_copy':
        try:
            db = get_db()
            cursor = db.cursor()
            
            cursor.execute(
                "INSERT INTO images (display_name, internal_filename, full_text, ocr_data_json) VALUES (?, ?, ?, ?)",
                (display_name, f"temp_{display_name}", "", "") 
            )
            db.commit()
            new_id = cursor.lastrowid

            name_parts = display_name.rsplit('.', 1)
            internal_filename = f"{name_parts[0]}_{new_id}.{name_parts[1]}"
            
            result, status_code = process_and_save_image(file, display_name, internal_filename)
            if status_code != 200:
                cursor.execute("DELETE FROM images WHERE id = ?", (new_id,))
                db.commit()
                return jsonify(result), status_code

            cursor.execute(
                "UPDATE images SET internal_filename = ?, full_text = ?, ocr_data_json = ? WHERE id = ?",
                (internal_filename, result['full_text'], result['ocr_data_json'], new_id)
            )
            db.commit()
            
            return jsonify({"message": "File added as new copy", "id": new_id}), 201

        except Exception as e:
            return jsonify({"error": f"Database error: {str(e)}"}), 500
    else:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], display_name)

        if os.path.exists(filepath):
            return jsonify({
                "error": "File already exists", 
                "message": f"A file named '{display_name}' already exists. What would you like to do?"
            }), 409 # 409 Conflict is the correct code
        
        try:
            result, status_code = process_and_save_image(file, display_name, display_name)
            if status_code != 200:
                 return jsonify(result), status_code

            db = get_db()
            cursor = db.cursor()
            cursor.execute(
                "INSERT INTO images (display_name, internal_filename, full_text, ocr_data_json) VALUES (?, ?, ?, ?)",
                (display_name, display_name, result['full_text'], result['ocr_data_json'])
            )
            db.commit()
            new_id = cursor.lastrowid
            
            return jsonify({
                "message": "File processed successfully", 
                "id": new_id,
                "filename": display_name
            }), 201
            
        except sqlite3.IntegrityError:
             return jsonify({"error": f"File '{display_name}' already exists in the database."}), 400
        except Exception as e:
            return jsonify({"error": f"An error occurred: {str(e)}"}), 500


@app.route('/search', methods=['GET'])
def search_images():
    """
    Searches the database for images matching the query.
    Implements Boolean (AND / OR) and Fuzzy/Substring Search.
    Returns data needed for highlighting.
    """
    query = request.args.get('q', '').lower().strip()
    if not query:
        return jsonify({"error": "No query provided"}), 400

    search_type = 'OR'
    
    if ' AND ' in query.upper():
        search_terms = [term.strip() for term in query.upper().split(' AND ')]
        search_type = 'AND'
    elif ' OR ' in query.upper():
        search_terms = [term.strip() for term in query.upper().split(' OR ')]
        search_type = 'OR'
    else:
        search_terms = [term.strip() for term in query.split(' ')]
        search_type = 'OR'
        
    search_terms = [term.lower() for term in search_terms if term]
    if not search_terms:
         return jsonify([])

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, display_name, internal_filename, full_text, ocr_data_json FROM images")
    all_images = cursor.fetchall()

    matches = []

    for image in all_images:
        image_data = dict(image)
        matched_words_data = []
        matched_word_bboxes = set()
        
        terms_found_count = 0

        try:
            words_in_image = json.loads(image_data['ocr_data_json'])
        except:
            words_in_image = []
            
        for term in search_terms:
            term_found_in_this_image = False
            
            for word_data in words_in_image:
                if is_fuzzy_match(word_data['text'], term):
                    term_found_in_this_image = True

                    bbox_tuple = tuple(word_data['bbox'])
                    if bbox_tuple not in matched_word_bboxes:
                        matched_words_data.append(word_data)
                        matched_word_bboxes.add(bbox_tuple)
            
            if term_found_in_this_image:
                terms_found_count += 1
    
    

        if search_type == 'AND' and terms_found_count == len(search_terms):
            matches.append({
                "id": image_data['id'],
                "display_name": image_data['display_name'],
                "internal_filename": image_data['internal_filename'], 
                "matched_words": matched_words_data
            })
            
        elif search_type == 'OR' and terms_found_count > 0:
            matches.append({
                "id": image_data['id'],
                "display_name": image_data['display_name'],
                "internal_filename": image_data['internal_filename'], 
                "matched_words": matched_words_data
            })

    return jsonify(matches)

@app.route('/images', methods=['GET'])
def get_all_images():
    """Gets all images from the database to display in the gallery."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, display_name, internal_filename FROM images ORDER BY id DESC")
    images = cursor.fetchall()
    
    image_list = [{
        "id": img['id'],
        "display_name": img['display_name'],
        "internal_filename": img['internal_filename'] 
    } for img in images]
    
    return jsonify(image_list)

@app.route('/image/<int:image_id>', methods=['DELETE'])
def delete_image(image_id):
    """
    Deletes an image from the database and the file system.
    """
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT internal_filename FROM images WHERE id = ?", (image_id,))
    image_record = cursor.fetchone()
    
    if image_record is None:
        return jsonify({"error": "Image not found in database"}), 404
        
    internal_filename = image_record['internal_filename']
    
    try:
        cursor.execute("DELETE FROM images WHERE id = ?", (image_id,))
        db.commit()

        filepath = os.path.join(app.config['UPLOAD_FOLDER'], internal_filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            print(f"Deleted file: {filepath}")
        else:
            print(f"File not found on disk (already deleted?): {filepath}")
            
        return jsonify({"message": f"Image {image_id} deleted successfully."}), 200
        
    except Exception as e:
        return jsonify({"error": f"An error occurred during deletion: {str(e)}"}), 500


@app.route('/uploads/<path:filename>')
def serve_image(filename):
    """Serves the uploaded images from the 'uploads' folder."""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    init_db()
    app.run(debug=True, port=5000)

