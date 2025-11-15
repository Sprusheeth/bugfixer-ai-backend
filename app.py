import os
import io
import zipfile
import google.generativeai as genai
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app) 

try:
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY environment variable not set.")
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    print(f"Error configuring Gemini: {e}")

def call_gemini_to_fix_code(files_data, instructions, opt_lint, opt_comments):
   
    if not files_data:
        return {}

    prompt_parts = [
        "You are an expert AI code-fixing agent, BugFixer.ai.",
        "A user has uploaded a project with the following files and structure.",
        "Your task is to fix the bug(s) described in their instructions, preserving the exact file structure.",
        "\n--- USER INSTRUCTIONS ---",
        instructions or "No specific instructions provided. Please analyze and fix any obvious bugs.",
        "\n--- OPTIONAL OPTIMIZATIONS ---",
        f"- Fix Linting Errors: {'Yes' if opt_lint else 'No'}",
        f"- Add Explanatory Comments: {'Yes' if opt_comments else 'No'}",
        "\n--- PROJECT FILES ---"
    ]

    for path, content in files_data.items():
        prompt_parts.append(f"\n--- File: {path} ---")
        prompt_parts.append(content)
        prompt_parts.append("--- End of File ---")
    
    prompt_parts.append("\n--- YOUR TASK ---")
    prompt_parts.append(
        "Generate the corrected code for all files that need changes. "
        "For each file you modify, you MUST provide the output in the following format, "
        "and only this format:"
    )
    prompt_parts.append(
        "START_FILE: [full/path/to/file.js]\n"
        "[... the complete, corrected code for this file ...]\n"
        "END_FILE"
    )
    prompt_parts.append("If a file does not need any changes, do not include it in your response.")

    prompt = "\n".join(prompt_parts)
    
    print("--- Sending prompt to Gemini ---")
    print("--------------------------------")

    try:
        response = model.generate_content(prompt)
        ai_response_text = response.text
        
        fixed_files = {}
        file_blocks = ai_response_text.split("START_FILE: ")
        
        for block in file_blocks:
            if not block.strip():
                continue
                
            parts = block.split("\n", 1)
            if len(parts) < 2:
                continue
                
            file_path = parts[0].strip()
            if "END_FILE" in parts[1]:
                code_content = parts[1].rsplit("END_FILE", 1)[0].strip()
                fixed_files[file_path] = code_content
            else:
                print(f"Warning: Could not find END_FILE for {file_path}")

        print(f"Gemini fixed {len(fixed_files)} files.")
        return fixed_files

    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return {"error": f"Error calling Gemini: {e}"}


@app.route('/api/fix', methods=['POST'])
def fix_code():
    if 'files' not in request.files:
        return jsonify({"error": "No files part"}), 400

    files = request.files.getlist('files')
    instructions = request.form.get('instructions', '')
    opt_lint = request.form.get('optLint') == '1'
    opt_comments = request.form.get('optComments') == '1'

    original_files = {}
    for file in files:
        original_files[file.filename] = file.read().decode('utf-8')

    fixed_files_map = call_gemini_to_fix_code(original_files, instructions, opt_lint, opt_comments)

    if "error" in fixed_files_map:
        return jsonify(fixed_files_map), 500

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for path, content in original_files.items():
         
            final_content = fixed_files_map.get(path, content)
            zf.writestr(path, final_content)

    zip_buffer.seek(0)
    
    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name='fixed_repo.zip'
    )

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))