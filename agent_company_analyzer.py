#!/usr/bin/env python3
"""
Agent 1: Company Information Analyzer
Analyzes uploaded PDF company data and extracts key information for RFP preparation.
"""

import os
import sys
from typing import List, Dict, Any, Optional
import json
from pathlib import Path
import PyPDF2
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage
from langchain.prompts import ChatPromptTemplate
import redis
import pandas as pd

# Load environment variables
load_dotenv()

class CompanyAnalyzerAgent:
    """Agent that analyzes company information from PDF documents."""
    
    def __init__(self, redis_url: str = "redis://localhost:6379", openai_api_key: str = None):
        """Initialize the Company Analyzer Agent."""
        self.redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.1,
            api_key=openai_api_key or os.getenv("OPENAI_API_KEY")
        )
        
        # Company analysis prompt template
        self.analysis_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a Company Information Analyzer Agent. Your role is to analyze company documents and extract key information that will be useful for RFP (Request for Proposal) preparation.

Extract and structure the following information from the company document:

1. **Company Overview**:
   - Company name
   - Industry/sector
   - Size (employees, revenue if mentioned)
   - Location(s)
   - Years in business

2. **Core Capabilities**:
   - Primary services/products
   - Technical expertise
   - Certifications/qualifications
   - Past project experience

3. **Financial Information**:
   - Revenue ranges
   - Budget capabilities
   - Financial stability indicators

4. **Compliance & Certifications**:
   - Industry certifications
   - Regulatory compliance
   - Quality standards (ISO, etc.)

5. **Key Personnel**:
   - Leadership team
   - Key technical staff
   - Project managers

6. **RFP Relevance**:
   - How this company could respond to government/municipal RFPs
   - Strengths for public sector work
   - Potential project types they could handle

Format your response as a structured JSON with clear sections and bullet points for easy consumption by the RFP drafting agent."""),
            ("human", "Analyze this company document and extract key information:\n\n{document_text}")
        ])
        
        print("✅ Company Analyzer Agent initialized")

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract text content from a PDF file or plain text file."""
        try:
            # Check if it's a text file first
            if pdf_path.endswith('.txt'):
                with open(pdf_path, 'r', encoding='utf-8') as file:
                    return file.read()
            
            # Otherwise, treat as PDF
            text_content = ""
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page_num, page in enumerate(pdf_reader.pages):
                    page_text = page.extract_text()
                    if page_text.strip():
                        text_content += f"\n--- Page {page_num + 1} ---\n{page_text}\n"
            
            return text_content.strip()
        except Exception as e:
            print(f"❌ Error extracting text from {pdf_path}: {e}")
            return ""

    def analyze_company_document(self, pdf_path: str) -> Dict[str, Any]:
        """Analyze a company PDF document and extract structured information."""
        try:
            # Extract text from PDF
            document_text = self.extract_text_from_pdf(pdf_path)
            if not document_text:
                return {"error": "Could not extract text from PDF"}
            
            # Analyze with LLM
            print(f"🔍 Analyzing company document: {Path(pdf_path).name}")
            
            # Create the prompt
            messages = self.analysis_prompt.format_messages(document_text=document_text)
            
            # Get analysis from LLM
            response = self.llm.invoke(messages)
            analysis_text = response.content
            
            # Try to parse as JSON, fallback to structured text
            try:
                analysis_data = json.loads(analysis_text)
            except json.JSONDecodeError:
                # If not valid JSON, structure the text response
                analysis_data = {
                    "company_analysis": analysis_text,
                    "document_source": Path(pdf_path).name,
                    "analysis_type": "company_information"
                }
            
            # Add metadata
            analysis_data["document_source"] = Path(pdf_path).name
            analysis_data["analysis_timestamp"] = str(pd.Timestamp.now())
            analysis_data["agent"] = "CompanyAnalyzerAgent"
            
            return analysis_data
            
        except Exception as e:
            print(f"❌ Error analyzing company document: {e}")
            return {"error": str(e)}

    def store_analysis(self, analysis_data: Dict[str, Any], company_id: str) -> bool:
        """Store company analysis in Redis for use by other agents."""
        try:
            # Store in Redis with a structured key
            key = f"company_analysis:{company_id}"
            self.redis_client.hset(key, mapping={
                "analysis": json.dumps(analysis_data),
                "timestamp": str(pd.Timestamp.now()),
                "status": "completed"
            })
            
            print(f"✅ Company analysis stored with key: {key}")
            return True
            
        except Exception as e:
            print(f"❌ Error storing analysis: {e}")
            return False

    def get_company_summary(self, analysis_data: Dict[str, Any]) -> str:
        """Generate a concise summary of company capabilities for RFP use."""
        try:
            summary_prompt = ChatPromptTemplate.from_messages([
                ("system", """Create a concise 2-3 paragraph summary of this company's key capabilities and strengths for RFP purposes. Focus on:
                - Core competencies
                - Relevant experience
                - Financial capacity
                - Why they would be a good fit for government/municipal projects"""),
                ("human", "Company analysis data:\n{analysis_data}")
            ])
            
            messages = summary_prompt.format_messages(analysis_data=json.dumps(analysis_data, indent=2))
            response = self.llm.invoke(messages)
            
            return response.content
            
        except Exception as e:
            print(f"❌ Error generating company summary: {e}")
            return "Error generating summary"

    def process_company_document(self, pdf_path: str, company_id: str = None) -> Dict[str, Any]:
        """Complete workflow: analyze document, store results, and return summary."""
        try:
            # Use filename as company_id if not provided
            if not company_id:
                company_id = Path(pdf_path).stem
            
            print(f"🏢 Processing company document for: {company_id}")
            
            # Analyze the document
            analysis_data = self.analyze_company_document(pdf_path)
            
            if "error" in analysis_data:
                return analysis_data
            
            # Store the analysis
            stored = self.store_analysis(analysis_data, company_id)
            
            # Generate summary
            summary = self.get_company_summary(analysis_data)
            
            result = {
                "company_id": company_id,
                "analysis_completed": True,
                "stored_in_redis": stored,
                "summary": summary,
                "full_analysis": analysis_data
            }
            
            print(f"✅ Company analysis completed for: {company_id}")
            return result
            
        except Exception as e:
            print(f"❌ Error processing company document: {e}")
            return {"error": str(e)}

def main():
    """Test the Company Analyzer Agent."""
    agent = CompanyAnalyzerAgent()
    
    # Example usage
    print("🏢 Company Analyzer Agent - Ready for document analysis")
    print("Usage: agent.process_company_document('path/to/company.pdf', 'company_name')")

if __name__ == "__main__":
    main()