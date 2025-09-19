#!/usr/bin/env python3
"""
Query Script for City Agent RAG Pipeline
Performs semantic search on ingested documents and generates answers with citations.
"""

import os
import sys
from typing import List, Dict, Any
import json
import numpy as np
from dotenv import load_dotenv
import redis
from openai import OpenAI

# Load environment variables
load_dotenv()

class CityAgentQuery:
    def __init__(self, redis_url: str = "redis://localhost:6379", openai_api_key: str = None):
        """Initialize the query system with Redis and OpenAI connections."""
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
        
    def get_embedding(self, text: str) -> List[float]:
        """Get embedding for query text using OpenAI's text-embedding-ada-002 model."""
        try:
            response = self.openai_client.embeddings.create(
                model="text-embedding-ada-002",
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"Error getting embedding: {e}")
            return None
    
    def search_documents(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search for relevant document chunks using vector similarity."""
        # Get query embedding
        query_embedding = self.get_embedding(query)
        if query_embedding is None:
            return []
        
        try:
            # Get all document keys
            doc_keys = self.redis_client.keys("doc:*")
            
            if not doc_keys:
                print("❌ No documents found in the database. Please run ingestion first.")
                return []
            
            # Calculate similarities (simplified approach)
            similarities = []
            for key in doc_keys:
                try:
                    doc_data = self.redis_client.hgetall(key)
                    if b'embedding' in doc_data:
                        # Embeddings are stored as JSON strings, not binary data
                        embedding_json = doc_data[b'embedding'].decode()
                        stored_embedding = np.array(json.loads(embedding_json), dtype=np.float32)
                        query_emb = np.array(query_embedding, dtype=np.float32)
                        
                        # Calculate cosine similarity
                        similarity = np.dot(query_emb, stored_embedding) / (
                            np.linalg.norm(query_emb) * np.linalg.norm(stored_embedding)
                        )
                        
                        similarities.append({
                            'key': key.decode(),
                            'similarity': similarity,
                            'content': doc_data[b'content'].decode(),
                            'filename': doc_data[b'filename'].decode(),
                            'page_number': int(doc_data[b'page_number']),
                            'chunk_id': doc_data[b'chunk_id'].decode()
                        })
                except Exception as e:
                    print(f"Error processing document {key.decode()}: {e}")
                    continue
            
            # Sort by similarity and return top_k
            similarities.sort(key=lambda x: x['similarity'], reverse=True)
            return similarities[:top_k]
            
        except Exception as e:
            print(f"Error searching documents: {e}")
            return []
    
    def generate_answer(self, query: str, context_chunks: List[Dict[str, Any]]) -> str:
        """Generate an answer using OpenAI's chat model with retrieved context."""
        if not context_chunks:
            return "I couldn't find any relevant information in the documents to answer your question."
        
        # Prepare context from retrieved chunks
        context_text = ""
        citations = []
        
        for i, chunk in enumerate(context_chunks, 1):
            context_text += f"[Source {i}] {chunk['content']}\\n\\n"
            citations.append({
                'source_num': i,
                'filename': chunk['filename'],
                'page': chunk['page_number'],
                'similarity': chunk['similarity']
            })
        
        # Create the prompt
        system_prompt = """You are a helpful assistant for city government staff. You answer questions based on provided document excerpts.

IMPORTANT INSTRUCTIONS:
1. Base your answer ONLY on the provided sources
2. Always include citations in your response using [Source X] format
3. If the sources don't contain enough information, say so clearly
4. Be specific and cite exact sources for each claim
5. Focus on actionable information for city staff"""

        user_prompt = f"""Question: {query}

Available Sources:
{context_text}

Please provide a comprehensive answer with proper citations."""

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=1000
            )
            
            answer = response.choices[0].message.content
            
            # Add citation details at the end
            citation_details = "\\n\\n📚 **Source Details:**\\n"
            for citation in citations:
                citation_details += f"[Source {citation['source_num']}] {citation['filename']}, Page {citation['page']} (Similarity: {citation['similarity']:.3f})\\n"
            
            return answer + citation_details
            
        except Exception as e:
            print(f"Error generating answer: {e}")
            return "I encountered an error while generating the answer. Please try again."
    
    def query(self, question: str, top_k: int = 5) -> str:
        """Main query function that combines search and answer generation."""
        print(f"🔍 Searching for: {question}")
        
        # Search for relevant chunks
        relevant_chunks = self.search_documents(question, top_k)
        
        if not relevant_chunks:
            return "❌ No relevant documents found. Please make sure documents are ingested first."
        
        print(f"📄 Found {len(relevant_chunks)} relevant chunks")
        
        # Generate answer with citations
        answer = self.generate_answer(question, relevant_chunks)
        
        return answer

def main():
    """Interactive query interface."""
    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Please set OPENAI_API_KEY in your .env file")
        sys.exit(1)
    
    # Initialize query system
    query_system = CityAgentQuery()
    
    print("🏛️  City Agent RAG System")
    print("=" * 50)
    print("Ask questions about your ingested city documents.")
    print("Type 'quit' or 'exit' to stop.\\n")
    
    while True:
        try:
            question = input("❓ Your question: ").strip()
            
            if question.lower() in ['quit', 'exit', 'q']:
                print("👋 Goodbye!")
                break
            
            if not question:
                continue
            
            # Get answer
            answer = query_system.query(question)
            
            print("\\n" + "=" * 50)
            print("🤖 **Answer:**")
            print(answer)
            print("=" * 50 + "\\n")
            
        except KeyboardInterrupt:
            print("\\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()