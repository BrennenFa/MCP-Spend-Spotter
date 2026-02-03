import os
import json
import chromadb
from pathlib import Path
from dotenv import load_dotenv
from llama_parse import LlamaParse
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv()
llama_key = os.getenv("LLAMA_INDEX")
pdf_path = str(Path(__file__).parent.parent / "data" / "budget-recommend.pdf")


# load keywords json
keywords_path = Path(__file__).parent.parent / "keywords" / "keywords.json"
with open(keywords_path, 'r') as f:
    keywords_data = json.load(f)

# parse
parser = LlamaParse(
    api_key=llama_key,
    result_type="markdown",
    parsing_instruction="""
        Extract ALL text, tables, and budget data exactly as they appear. 
        Identify sections with ## headers and sub-sections with ###. 
        DO NOT summarize. Include every line item.
    """
)
documents = parser.load_data(pdf_path)
full_markdown = "\n\n".join([doc.text for doc in documents])


headers_to_split_on = [
    ("##", "Section"),
    ("###", "SubSection"),
]

header_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
sections = header_splitter.split_text(full_markdown)

# recursive sub split - prevent chunks from being too big for the AI
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000, 
    chunk_overlap=150
)
final_chunks = text_splitter.split_documents(sections)

# Function to process keyword matching for a single chunk
def process_chunk_keywords(chunk, keywords_data):
    chunk_text_lower = chunk.page_content.lower()
    for category, keywords in keywords_data.items():
        found_keywords = [keyword for keyword in keywords if f" {keyword.lower()} " in chunk_text_lower]
        if found_keywords:
            if category not in chunk.metadata:
                chunk.metadata[category] = []
            chunk.metadata[category].extend(found_keywords)
    return chunk

# Process chunks in parallel for keyword matching
print(f"\nProcessing {len(final_chunks)} chunks with {os.cpu_count()} threads for keyword matching...")
with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
    final_chunks = list(executor.map(lambda chunk: process_chunk_keywords(chunk, keywords_data), final_chunks))
print("Keyword matching complete!")

# vectorize every chunk
model = SentenceTransformer("all-MiniLM-L6-v2")


# Prepare the texts for the model
texts_to_embed = [chunk.page_content for chunk in final_chunks]
vectors = model.encode(texts_to_embed, show_progress_bar=True)


# OUTPUT FINAL RESULTS
print("\n" + "="*50)
print(f"SUCCESS: CREATED {len(final_chunks)} VECTORS")
print("="*50 + "\n")

# Show a sample of a chunk with its new structural metadata
sample_index = 0
print(f"--- SAMPLE CHUNK {sample_index+1} ---")
print(f"Metadata (Header Path): {final_chunks[sample_index].metadata}")
print(f"Text Preview: {final_chunks[sample_index].page_content}...")
print(f"Vector: {vectors[sample_index][:5]}")


# Initialize ChromaDB client and collection
db_path = Path(__file__).parent.parent / "db"
client = chromadb.PersistentClient(path=str(db_path))
collection = client.get_or_create_collection(name="budget_documents")

# Function to prepare metadata for a single chunk
def prepare_chunk_metadata(chunk):
    metadata = {}
    for key, value in chunk.metadata.items():
        if isinstance(value, list):
            metadata[key] = ",".join(map(str, value))
        else:
            metadata[key] = value
    return metadata

# Prepare data for ChromaDB
chunk_ids = [str(i) for i in range(len(final_chunks))]
chunk_docs = [chunk.page_content for chunk in final_chunks]

# Process metadata preparation in parallel
print(f"\nPreparing metadata for {len(final_chunks)} chunks with {os.cpu_count()} threads...")
with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
    chunk_metadata = list(executor.map(prepare_chunk_metadata, final_chunks))
print("Metadata preparation complete!")

# Add to ChromaDB
collection.add(
    embeddings=vectors.tolist(),
    documents=chunk_docs,
    metadatas=chunk_metadata,
    ids=chunk_ids
)

print("\n" + "="*50)
print(f"SUCCESS: ADDED {len(final_chunks)} CHUNKS TO CHROMA DB")
print("="*50 + "\n")