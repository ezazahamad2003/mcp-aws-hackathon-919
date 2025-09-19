#!/usr/bin/env python3
"""
Agent 2: RFP Drafter
Drafts RFP (Request for Proposal) documents based on county policies and budget constraints.
Uses the Redis vector index to ensure compliance with existing policies and budget allocations.
"""

import os
import sys
from typing import List, Dict, Any, Optional
import json
from datetime import datetime, timedelta
import redis
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage
from langchain.prompts import ChatPromptTemplate
import numpy as np
from query import CityAgentQuery

# Load environment variables
load_dotenv()

class RFPDrafterAgent:
    """Agent that drafts RFP documents based on county policies and budget constraints."""
    
    def __init__(self, redis_url: str = "redis://localhost:6379", openai_api_key: str = None):
        """Initialize the RFP Drafter Agent."""
        self.redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.3,
            api_key=openai_api_key or os.getenv("OPENAI_API_KEY")
        )
        
        # Initialize the query system to access county policies and budget data
        self.policy_query = CityAgentQuery()
        
        # RFP drafting prompt template
        self.rfp_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an RFP Drafter Agent specializing in creating Request for Proposal documents for municipal/county projects. Your role is to draft comprehensive, compliant RFPs that align with county policies and budget constraints.

Create a professional RFP document with the following structure:

1. **PROJECT OVERVIEW**
   - Project title and description
   - Background and justification
   - Project objectives and scope

2. **BUDGET AND FINANCIAL REQUIREMENTS**
   - Total project budget (based on county budget data)
   - Payment terms and schedule
   - Cost breakdown requirements

3. **TECHNICAL REQUIREMENTS**
   - Detailed specifications
   - Performance standards
   - Deliverables and timeline

4. **VENDOR QUALIFICATIONS**
   - Required experience and expertise
   - Certification requirements
   - Past performance criteria

5. **COMPLIANCE REQUIREMENTS**
   - County policy compliance
   - Regulatory requirements
   - Insurance and bonding requirements

6. **EVALUATION CRITERIA**
   - Scoring methodology
   - Selection criteria weights
   - Evaluation process

7. **SUBMISSION REQUIREMENTS**
   - Proposal format and content
   - Submission deadline and method
   - Contact information

Ensure the RFP is:
- Compliant with county policies and procedures
- Within approved budget allocations
- Clear and comprehensive for vendors
- Legally sound and fair

Format as a professional RFP document with proper sections and numbering."""),
            ("human", """Draft an RFP for the following project:

PROJECT REQUEST: {project_description}

COMPANY INFORMATION: {company_analysis}

COUNTY POLICY CONTEXT: {policy_context}

BUDGET CONSTRAINTS: {budget_context}

Please create a comprehensive RFP that addresses all requirements while ensuring compliance with county policies and budget limitations.""")
        ])
        
        print("✅ RFP Drafter Agent initialized")

    def get_policy_context(self, project_type: str, keywords: List[str]) -> str:
        """Query the Redis index for relevant county policies and procedures."""
        try:
            # Search for relevant policies
            policy_queries = [
                f"county policies for {project_type}",
                f"procurement requirements {project_type}",
                f"budget allocation {project_type}",
                "RFP requirements and procedures"
            ]
            
            # Add specific keywords to queries
            for keyword in keywords:
                policy_queries.append(f"county policy {keyword}")
            
            all_context = []
            
            for query in policy_queries:
                print(f"🔍 Searching policies for: {query}")
                results = self.policy_query.search_documents(query, top_k=3)
                
                for result in results:
                    context_item = {
                        "source": result.get('filename', 'Unknown'),
                        "page": result.get('page_number', 'N/A'),
                        "content": result.get('content', ''),
                        "relevance": result.get('similarity', 0)
                    }
                    all_context.append(context_item)
            
            # Format context for RFP drafting
            formatted_context = "\\n\\n".join([
                f"**{item['source']} (Page {item['page']})**\\n{item['content']}"
                for item in all_context[:10]  # Limit to top 10 most relevant
            ])
            
            return formatted_context
            
        except Exception as e:
            print(f"❌ Error retrieving policy context: {e}")
            return "Policy context unavailable - please ensure compliance manually."

    def get_budget_context(self, project_type: str, estimated_budget: Optional[float] = None) -> str:
        """Query the Redis index for relevant budget information and constraints."""
        try:
            budget_queries = [
                f"budget allocation {project_type}",
                f"total budget {project_type}",
                "capital budget operating budget",
                "city budget funding"
            ]
            
            if estimated_budget:
                budget_queries.append(f"budget {estimated_budget}")
            
            budget_context = []
            
            for query in budget_queries:
                print(f"💰 Searching budget info for: {query}")
                results = self.policy_query.search_documents(query, top_k=2)
                
                for result in results:
                    budget_item = {
                        "source": result.get('filename', 'Unknown'),
                        "page": result.get('page_number', 'N/A'),
                        "content": result.get('content', ''),
                        "relevance": result.get('similarity', 0)
                    }
                    budget_context.append(budget_item)
            
            # Format budget context
            formatted_budget = "\\n\\n".join([
                f"**Budget Source: {item['source']} (Page {item['page']})**\\n{item['content']}"
                for item in budget_context[:5]  # Top 5 budget references
            ])
            
            return formatted_budget
            
        except Exception as e:
            print(f"❌ Error retrieving budget context: {e}")
            return "Budget context unavailable - please verify budget allocations manually."

    def get_company_analysis(self, company_id: str) -> Dict[str, Any]:
        """Retrieve company analysis from Redis storage."""
        try:
            key = f"company_analysis:{company_id}"
            stored_data = self.redis_client.hgetall(key)
            
            if stored_data and 'analysis' in stored_data:
                analysis = json.loads(stored_data['analysis'])
                return analysis
            else:
                return {"error": f"No company analysis found for {company_id}"}
                
        except Exception as e:
            print(f"❌ Error retrieving company analysis: {e}")
            return {"error": str(e)}

    def draft_rfp(self, project_description: str, company_id: str, project_type: str = "general", 
                  keywords: List[str] = None, estimated_budget: Optional[float] = None) -> Dict[str, Any]:
        """Draft a comprehensive RFP document."""
        try:
            print(f"📝 Drafting RFP for project: {project_description[:50]}...")
            
            # Get company analysis
            company_analysis = self.get_company_analysis(company_id)
            if "error" in company_analysis:
                print(f"⚠️ Warning: {company_analysis['error']}")
                company_analysis = {"note": "Company analysis not available"}
            
            # Get policy context from Redis index
            policy_context = self.get_policy_context(project_type, keywords or [])
            
            # Get budget context from Redis index
            budget_context = self.get_budget_context(project_type, estimated_budget)
            
            # Create the RFP using LLM
            messages = self.rfp_prompt.format_messages(
                project_description=project_description,
                company_analysis=json.dumps(company_analysis, indent=2),
                policy_context=policy_context,
                budget_context=budget_context
            )
            
            print("🤖 Generating RFP document...")
            response = self.llm.invoke(messages)
            rfp_content = response.content
            
            # Create RFP metadata
            rfp_data = {
                "rfp_content": rfp_content,
                "project_description": project_description,
                "company_id": company_id,
                "project_type": project_type,
                "keywords": keywords or [],
                "estimated_budget": estimated_budget,
                "created_timestamp": datetime.now().isoformat(),
                "agent": "RFPDrafterAgent",
                "policy_sources_used": len(policy_context.split("**")) - 1,
                "budget_sources_used": len(budget_context.split("**")) - 1
            }
            
            return rfp_data
            
        except Exception as e:
            print(f"❌ Error drafting RFP: {e}")
            return {"error": str(e)}

    def save_rfp(self, rfp_data: Dict[str, Any], rfp_id: str) -> bool:
        """Save the drafted RFP to Redis and as a file."""
        try:
            # Save to Redis
            key = f"rfp_draft:{rfp_id}"
            self.redis_client.hset(key, mapping={
                "rfp_data": json.dumps(rfp_data),
                "timestamp": datetime.now().isoformat(),
                "status": "drafted"
            })
            
            # Save as text file
            filename = f"RFP_{rfp_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = os.path.join(os.getcwd(), filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"RFP DOCUMENT - {rfp_id}\\n")
                f.write("=" * 50 + "\\n\\n")
                f.write(rfp_data.get('rfp_content', ''))
                f.write("\\n\\n" + "=" * 50 + "\\n")
                f.write(f"Generated: {rfp_data.get('created_timestamp', '')}\\n")
                f.write(f"Project Type: {rfp_data.get('project_type', '')}\\n")
                f.write(f"Company ID: {rfp_data.get('company_id', '')}\\n")
            
            print(f"✅ RFP saved to Redis (key: {key}) and file: {filename}")
            return True
            
        except Exception as e:
            print(f"❌ Error saving RFP: {e}")
            return False

    def create_rfp_workflow(self, project_description: str, company_id: str, 
                           project_type: str = "general", keywords: List[str] = None,
                           estimated_budget: Optional[float] = None, rfp_id: str = None) -> Dict[str, Any]:
        """Complete RFP creation workflow."""
        try:
            # Generate RFP ID if not provided
            if not rfp_id:
                rfp_id = f"{project_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            print(f"🚀 Starting RFP creation workflow for: {rfp_id}")
            
            # Draft the RFP
            rfp_data = self.draft_rfp(
                project_description=project_description,
                company_id=company_id,
                project_type=project_type,
                keywords=keywords,
                estimated_budget=estimated_budget
            )
            
            if "error" in rfp_data:
                return rfp_data
            
            # Save the RFP
            saved = self.save_rfp(rfp_data, rfp_id)
            
            result = {
                "rfp_id": rfp_id,
                "creation_successful": True,
                "saved_to_storage": saved,
                "rfp_preview": rfp_data.get('rfp_content', '')[:500] + "...",
                "metadata": {
                    "project_type": project_type,
                    "company_id": company_id,
                    "estimated_budget": estimated_budget,
                    "policy_sources": rfp_data.get('policy_sources_used', 0),
                    "budget_sources": rfp_data.get('budget_sources_used', 0)
                }
            }
            
            print(f"✅ RFP creation workflow completed for: {rfp_id}")
            return result
            
        except Exception as e:
            print(f"❌ Error in RFP creation workflow: {e}")
            return {"error": str(e)}

def main():
    """Test the RFP Drafter Agent."""
    agent = RFPDrafterAgent()
    
    print("📝 RFP Drafter Agent - Ready for RFP creation")
    print("Usage: agent.create_rfp_workflow(project_description, company_id, project_type, keywords, budget)")

if __name__ == "__main__":
    main()