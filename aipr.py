import subprocess
import openai
import os
import difflib
import re
import json

# Environment variables
issue_title = os.environ["ISSUE_TITLE"]
issue_body = os.environ["ISSUE_BODY"]
open_ai_api_key = os.environ["OPENAI_API_KEY"]
open_ai_tokens = os.environ["OPENAI_TOKENS"]
open_ai_model = os.environ["OPENAI_MODEL"]
chunks = os.environ["FILE_CHUNKS"]
directory = os.getenv("TARGET_DIRECTORY", "./")  # Default to current directory if not specified

# Step 1: Set up OpenAI API client
openai.api_key = open_ai_api_key
question = issue_body

# Step 2: Read all files from a local repository
def read_all_files_from_directory(directory):
    file_contents = {}
    for root, _, files in os.walk(directory):
        for file in files:
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                file_contents[filepath] = f.read()
    return file_contents

def split_into_chunks(text, chunk_size):
    """
    Splits a text into chunks, each of a maximum size of chunk_size.
    """
    chunks = []
    while text:
        chunk = text[:chunk_size]
        text = text[chunk_size:]
        chunks.append(chunk)
    return chunks

# Step 3: Query OpenAI for changes
def request_changes_from_openai(context, filename):
    try:
        response = openai.Completion.create(
            model=open_ai_model or "gpt-4o",
            prompt=f"Giving the filename:'{filename}' and the following content:'{context}'\n modify the content to provide a solution for this issue:\n'{question}'\n and output the result.",
            max_tokens=int(open_ai_tokens) or 200
        )
        return response.choices[0].text.strip() if response.choices else context
    except Exception as e:
        print(f"Error querying OpenAI for {filename}: {e}")
        return context

def request_changes_from_openai_in_chunks(context, filename, max_chunk_size):
    """
    Request changes from OpenAI by processing the content in chunks.
    """
    chunks = split_into_chunks(context, max_chunk_size)
    modified_chunks = []

    for chunk in chunks:
        try:
            response = openai.Completion.create(
                model=open_ai_model if len(open_ai_model) else "gpt-4o",
                prompt=f"Giving the filename:'{filename}' and the following content:'{chunk}'\n modify the content to provide a solution for this issue:\n'{question}'\n and output the result.",
                max_tokens=int(open_ai_tokens) or 200
            )
            modified_chunks.append(response.choices[0].text.strip())
        except Exception as e:
            print(f"Error processing chunk for {filename}: {e}")
            modified_chunks.append(chunk)  # Use original chunk if an error occurs

    return "".join(modified_chunks)

# Generate patch
def generate_patch(original, modified, filename):
    original_lines = original.splitlines(keepends=True)
    modified_lines = modified.splitlines(keepends=True)
    d = difflib.unified_diff(original_lines, modified_lines, fromfile=filename, tofile=filename)
    return ''.join(d)

# Extract file paths from the issue body
def extract_specific_file_path(text):
    regex = r"(\.?\/[\w\/.-]+\.\w+)"
    return re.findall(regex, text)

# Main script
if __name__ == "__main__":
    all_files = read_all_files_from_directory(directory)
    patches = {}
    files_in_prompt = extract_specific_file_path(question)
    files_in_prompt_full_path = [os.path.abspath(os.path.join(directory, x.lstrip("."))) for x in files_in_prompt]

    for filename, content in all_files.items():
        if filename in files_in_prompt_full_path:
            print(f"Processing file: {filename}")
            modified_content = request_changes_from_openai(content, filename) if int(chunks) == 0 else request_changes_from_openai_in_chunks(content, filename, int(chunks))
            patch = generate_patch(content, modified_content, filename)
            if patch.strip():
                patches[filename] = patch
                print(f"Generated patch for {filename}:\n{patch}")
            else:
                print(f"No changes detected for {filename}.")

    # Save patches to a file
    if patches:
        with open("changes.patch", "w") as f:
            for filename, patch in patches.items():
                f.write(patch)
                f.write('\n\n')
    else:
        print("No patches generated. Skipping file creation.")

    # Validate and apply patch
    if os.path.exists("changes.patch") and os.path.getsize("changes.patch") > 0:
        print("Validating patch file...")
        result = subprocess.run(["git", "apply", "--check", "changes.patch"], capture_output=True, text=True)
        if result.returncode == 0:
            subprocess.run(["git", "apply", "changes.patch"], check=True)
        else:
            print(f"Patch check failed: {result.stderr}")
    else:
        print("No valid patches detected. Skipping git apply.")
