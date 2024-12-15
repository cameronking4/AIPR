import subprocess
import openai
import os
import difflib
import re
import json

# Environment variables with default values and validation
issue_title = os.getenv("ISSUE_TITLE", "Default Issue Title")
issue_body = os.getenv("ISSUE_BODY", "Default issue description.")
open_ai_api_key = os.getenv("OPENAI_API_KEY")
open_ai_tokens = os.getenv("OPENAI_TOKENS", "200")
open_ai_model = os.getenv("OPENAI_MODEL", "gpt-4o")
chunks = os.getenv("FILE_CHUNKS", "0")
directory = os.getenv("TARGET_DIRECTORY", "./")  # Default to current directory if not specified

# Validate essential environment variables
if not open_ai_api_key:
    raise ValueError("The OPENAI_API_KEY environment variable is not set.")

# Convert numeric environment variables to integers with error handling
try:
    open_ai_tokens = int(open_ai_tokens)
except ValueError:
    raise ValueError("OPENAI_TOKENS must be an integer.")

try:
    chunks = int(chunks)
except ValueError:
    raise ValueError("FILE_CHUNKS must be an integer.")

# Set up OpenAI API client
openai.api_key = open_ai_api_key
question = issue_body

# Function to read all files from a local repository
def read_all_files_from_directory(directory):
    file_contents = {}
    for root, _, files in os.walk(directory):
        for file in files:
            filepath = os.path.join(root, file)
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    file_contents[filepath] = f.read()
            except Exception as e:
                print(f"Error reading file {filepath}: {e}")
    return file_contents

# Function to split text into chunks
def split_into_chunks(text, chunk_size):
    chunks = []
    while text:
        chunk = text[:chunk_size]
        text = text[chunk_size:]
        chunks.append(chunk)
    return chunks

# Function to request changes from OpenAI
def request_changes_from_openai(context, filename):
    try:
        response = openai.Completion.create(
            model=open_ai_model,
            prompt=(
                f"Given the filename: '{filename}' and the following content:\n"
                f"'{context}'\n"
                f"Modify the content to provide a solution for this issue:\n"
                f"'{question}'\n"
                f"and output the result."
            ),
            max_tokens=open_ai_tokens
        )
        print(response.choices[0])
        return response.choices[0].text.strip() if response.choices else context
    except Exception as e:
        print(f"Error querying OpenAI for {filename}: {e}")
        return context

# Function to request changes from OpenAI in chunks
def request_changes_from_openai_in_chunks(context, filename, max_chunk_size):
    chunks = split_into_chunks(context, max_chunk_size)
    modified_chunks = []

    for chunk in chunks:
        modified_chunk = request_changes_from_openai(chunk, filename)
        modified_chunks.append(modified_chunk)

    return "".join(modified_chunks)

# Function to generate a patch
def generate_patch(original, modified, filename):
    original_lines = original.splitlines(keepends=True)
    modified_lines = modified.splitlines(keepends=True)
    diff = difflib.unified_diff(original_lines, modified_lines, fromfile=filename, tofile=filename)
    return ''.join(diff)

# Function to extract file paths from the issue body
def extract_specific_file_paths(text):
    regex = r"(\.?\/[\w\/.-]+\.\w+)"
    return re.findall(regex, text)

# Main script execution
if __name__ == "__main__":
    all_files = read_all_files_from_directory(directory)
    patches = {}
    files_in_prompt = extract_specific_file_paths(question)
    files_in_prompt_full_path = [os.path.abspath(os.path.join(directory, x.lstrip("."))) for x in files_in_prompt]

    for filename, content in all_files.items():
        if filename in files_in_prompt_full_path:
            print(f"Processing file: {filename}")
            if chunks > 0:
                modified_content = request_changes_from_openai_in_chunks(content, filename, chunks)
            else:
                modified_content = request_changes_from_openai(content, filename)
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
        print("Patches saved to 'changes.patch'.")
    else:
        print("No patches generated. Skipping file creation.")

    # Validate and apply patch
    if os.path.exists("changes.patch") and os.path.getsize("changes.patch") > 0:
        print("Validating patch file...")
        result = subprocess.run(["git", "apply", "--check", "changes.patch"], capture_output=True, text=True)
        if result.returncode == 0:
            try:
                subprocess.run(["git", "apply", "changes.patch"], check=True)
                print("Patch applied successfully.")
            except subprocess.CalledProcessError as e:
                print(f"Error applying patch: {e}")
        else:
            print(f"Patch check failed: {result.stderr}")
    else:
        print("No valid patches detected. Skipping git apply.")
