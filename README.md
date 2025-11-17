**IntelliGallery**

A White-Box, Error-Tolerant Search Framework for Private Image Repositories.

**Overview**

IntelliGallery is a local-first client–server system that transforms a private image collection into a searchable text index. The backend uses EasyOCR to extract text from images, stores structured OCR data in SQLite, and exposes a transparent, controllable search engine that supports Boolean (AND/OR) operations, substring detection, and fuzzy (Levenshtein) matching. All processing occurs locally, preserving privacy and ensuring predictable behavior.

**Key Features**

Local-first architecture with no cloud dependency.

High-accuracy printed + handwritten OCR through EasyOCR.

Explicit Boolean search logic (AND / OR).

Error-tolerant fuzzy matching for typos and OCR mistakes.

Substring detection (e.g., “time” in “timetable”).

Highlight overlays showing exactly where matched text appears.

Controlled duplicate handling workflow using HTTP 409 responses.


**Installation**

**1. Clone and enter the repository**

git clone https://github.com/kotaharshith/IntelliGallery.git

cd IntelliGallery

**2. Install dependencies**

pip install -r requirements.txt

**3. Start the Flask backend**

python app.py

**4. Open the frontend**

Open index.html in a browser (or use VS Code Live Server).



**How It Works:**

1.User uploads an image from the frontend.

2.Backend extracts text + bounding boxes with EasyOCR.

3.OCR data is stored as JSON in SQLite.

4.User enters a search query using keywords or AND/OR logic.

5.Backend performs substring and fuzzy matching across all images.

6.Images containing at least one matching word (OR) or all words (AND) are returned.

7.Frontend displays highlight overlays using the saved bounding boxes.

**Example Queries:**

invoice → returns images containing the word.

budget AND 2025 → both terms must appear.

meeting OR task → either term is valid.

invo1ce → matched through fuzzy (Levenshtein) logic.


**Technologies Used:**

Frontend: HTML5, TailwindCSS, JavaScript

Backend: Python Flask

OCR Engine: EasyOCR

Database: SQLite

Matching Logic: Boolean filtering + Levenshtein distance


**Future Enhancements:**

Multimodal search combining OCR text with object detection.

Semantic vector search using Sentence-BERT embeddings.

Knowledge graph creation using entity extraction for richer queries.


**License**

This project is intended for research and academic use.

All code © 2025 IntelliGallery Project Team.
