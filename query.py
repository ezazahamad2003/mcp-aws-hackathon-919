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
        """Search for relevant document chunks using Redis vector similarity search."""
        # Get query embedding
        query_embedding = self.get_embedding(query)
        if query_embedding is None:
            return []
        
        try:
            # Convert query embedding to bytes for Redis vector search
            query_vector = np.array(query_embedding, dtype=np.float32).tobytes()
            
            # Use Redis FT.SEARCH with vector similarity
            # KNN search syntax: *=>[KNN num @field $param]
            search_query = f"*=>[KNN {top_k} @embedding $vec]"
            
            # Execute vector search
            results = self.redis_client.execute_command(
                "FT.SEARCH", 
                "index2Z",  # index name
                search_query,
                "PARAMS", "2", "vec", query_vector,
                "RETURN", "4", "content", "filename", "page_number", "chunk_id",
                "DIALECT", "2"
            )
            
            if not results or len(results) < 2:
                print("❌ No documents found in the database. Please run ingestion first.")
                return []
            
            # Parse results
            total_results = results[0]
            documents = []
            
            # Results format: [total_count, doc_id1, [field1, value1, field2, value2, ...], doc_id2, [...], ...]
            for i in range(1, len(results), 2):
                if i + 1 < len(results):
                    doc_id = results[i]
                    doc_fields = results[i + 1]
                    
                    # Parse fields into a dictionary
                    doc_data = {}
                    for j in range(0, len(doc_fields), 2):
                        if j + 1 < len(doc_fields):
                            field_name = doc_fields[j]
                            field_value = doc_fields[j + 1]
                            
                            if isinstance(field_name, bytes):
                                field_name = field_name.decode()
                            if isinstance(field_value, bytes) and field_name != 'embedding':
                                field_value = field_value.decode()
                            
                            doc_data[field_name] = field_value
                    
                    # Add to results (similarity score is implicit in order)
                    if 'content' in doc_data:
                        documents.append({
                            'key': doc_id.decode() if isinstance(doc_id, bytes) else doc_id,
                            'content': doc_data.get('content', ''),
                            'filename': doc_data.get('filename', ''),
                            'page_number': int(doc_data.get('page_number', 0)),
                            'chunk_id': doc_data.get('chunk_id', ''),
                            'similarity': 1.0 - (len(documents) * 0.1)  # Approximate similarity based on rank
                        })
            
            return documents
            
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