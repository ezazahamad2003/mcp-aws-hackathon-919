#!/usr/bin/env python3
"""
Document Ingestion Script for City Agent RAG Pipeline
Extracts text from PDFs, creates embeddings, and stores in Redis for semantic search.
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Any
import PyPDF2
from dotenv import load_dotenv
import redis
from openai import OpenAI
import numpy as np
import json
from redisvl.index import SearchIndex

# Load environment variables
load_dotenv()

class DocumentIngester:
    def __init__(self, redis_url: str = "redis://localhost:6379", openai_api_key: str = None):
        """Initialize the document ingester with Redis and OpenAI connections."""
        self.redis_url = redis_url
        self.openai_client = OpenAI(api_key=openai_api_key or os.getenv("OPENAI_API_KEY"))
        
        # Initialize Redis connection
        self.redis_client = redis.from_url(redis_url, decode_responses=False)
        
        # Test connection
        try:
            self.redis_client.ping()
            print("✅ Connected to Redis")
        except Exception as e:
            print(f"❌ Failed to connect to Redis: {e}")
            raise
        
    def extract_text_from_pdf(self, pdf_path: str) -> List[Dict[str, Any]]:
        """Extract text from PDF file, returning pages with text."""
        pages = []
        
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                
                for page_num, page in enumerate(pdf_reader.pages):
                    text = page.extract_text()
                    
                    if text.strip():  # Only process pages with text
                        pages.append({
                            'text': text,
                            'page_number': page_num + 1
                        })
                                
        except Exception as e:
            print(f"Error extracting text from {pdf_path}: {e}")
            
        return pages
    
    def chunk_text(self, text: str, page_number: int) -> List[Dict[str, Any]]:
        """Split text into smaller chunks for better embedding and retrieval."""
        chunks = []
        words = text.split()
        chunk_size = 500  # words per chunk
        
        for i in range(0, len(words), chunk_size):
            chunk_words = words[i:i + chunk_size]
            chunk_text = ' '.join(chunk_words)
            
            if len(chunk_text.strip()) > 50:  # Only keep substantial chunks
                chunks.append({
                    'text': chunk_text,
                    'page_number': page_number
                })
        
        return chunks
    
    def generate_embedding(self, text: str) -> List[float]:
        """Get embedding for text using OpenAI's text-embedding-ada-002 model."""
        try:
            response = self.openai_client.embeddings.create(
                model="text-embedding-ada-002",
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"Error getting embedding: {e}")
            return None
    
    def create_index(self):
        """Create a proper Redis vector index using redisvl."""
        try:
            index_name = "index2Z"
            
            schema = {
                "index": {
                    "name": index_name,
                    "prefix": "doc"
                },
                "fields": [
                    {
                        "name": "chunk_id",
                        "type": "tag",
                        "attrs": {"sortable": True}
                    },
                    {
                        "name": "filename",
                        "type": "tag"
                    },
                    {
                        "name": "page_number",
                        "type": "numeric",
                        "attrs": {"sortable": True}
                    },
                    {
                        "name": "content",
                        "type": "text"
                    },
                    {
                        "name": "embedding",
                        "type": "vector",
                        "attrs": {
                            "dims": 1536,  # OpenAI ada-002 embedding dimension
                            "distance_metric": "cosine",
                            "algorithm": "flat",
                            "datatype": "float32"
                        }
                    }
                ]
            }
            
            # Create the index
            self.index = SearchIndex.from_dict(schema, redis_url=self.redis_url)
            self.index.create(overwrite=True, drop=True)
            print("✅ Created Redis vector index with proper schema")
            
        except Exception as e:
            print(f"❌ Error creating Redis index: {e}")
            raise
    
    def ingest_document(self, pdf_path: str) -> bool:
        """Ingest a PDF document into Redis with embeddings."""
        try:
            print(f"📄 Processing document: {pdf_path}")
            
            # Extract text from PDF
            pages = self.extract_text_from_pdf(pdf_path)
            if not pages:
                print("❌ No text extracted from PDF")
                return False
            
            # Create chunks and embeddings
            all_chunks = []
            for page in pages:
                chunks = self.chunk_text(page['text'], page['page_number'])
                all_chunks.extend(chunks)
            
            print(f"📝 Created {len(all_chunks)} text chunks")
            
            # Generate embeddings and store in Redis using the vector index
            filename = Path(pdf_path).name
            for i, chunk in enumerate(all_chunks):
                try:
                    # Generate embedding
                    embedding = self.generate_embedding(chunk['text'])
                    if embedding is None:
                        continue
                    
                    # Create document data for redisvl
                    doc_data = {
                        'chunk_id': f"{filename}_chunk_{i}",
                        'filename': filename,
                        'page_number': chunk['page_number'],
                        'content': chunk['text'],
                        'embedding': np.array(embedding, dtype=np.float32).tobytes()  # Convert to bytes
                    }
                    
                    # Store using redisvl index
                    self.index.load([doc_data])
                    
                    if i % 10 == 0:  # Progress indicator
                        print(f"  Processed {i+1}/{len(all_chunks)} chunks")
                        
                except Exception as e:
                    print(f"Error processing chunk {i}: {e}")
                    continue
            
            print(f"✅ Successfully ingested {filename} with {len(all_chunks)} chunks")
            return True
            
        except Exception as e:
            print(f"❌ Error ingesting document: {e}")
            return False
    
    def ingest_directory(self, directory_path: str) -> int:
        """Ingest all PDF files in a directory."""
        directory = Path(directory_path)
        pdf_files = list(directory.glob("*.pdf"))
        
        if not pdf_files:
            print(f"❌ No PDF files found in {directory_path}")
            return 0
        
        print(f"📁 Found {len(pdf_files)} PDF files to process")
        
        successful_docs = 0
        for pdf_file in pdf_files:
            if self.ingest_document(str(pdf_file)):
                successful_docs += 1
        
        print(f"\\n🎉 Successfully processed {successful_docs}/{len(pdf_files)} documents")
        return successful_docs

def main():
    """Main function to run document ingestion."""
    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Please set OPENAI_API_KEY in your .env file")
        sys.exit(1)
    
    # Initialize ingester
    ingester = DocumentIngester()
    
    # Create the vector index
    ingester.create_index()
    
    # Ingest documents from current directory
    current_dir = Path.cwd()
    ingester.ingest_directory(str(current_dir))

if __name__ == "__main__":
    main()