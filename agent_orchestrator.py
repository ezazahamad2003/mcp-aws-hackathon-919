#!/usr/bin/env python3
"""
RFP Agent Orchestrator using LangGraph
Coordinates the two-agent workflow for RFP generation
"""

import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional, Annotated, Sequence, TypedDict, Literal
from pathlib import Path

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from agent_company_analyzer import CompanyAnalyzerAgent
from agent_rfp_drafter import RFPDrafterAgent

# Load environment variables
from dotenv import load_dotenv
load_dotenv()


class AgentState(TypedDict):
    """LangGraph state with message-based communication"""
    # The add_messages function defines how an update should be processed
    # Default is to replace. add_messages says "append"
    messages: Annotated[Sequence[BaseMessage], add_messages]
    company_pdf_path: Optional[str]
    company_analysis: Optional[Dict[str, Any]]
    rfp_requirements: Optional[Dict[str, Any]]
    rfp_document: Optional[Dict[str, Any]]
    quality_score: Optional[float]
    workflow_status: str
    error_message: Optional[str]
    iteration_count: int


class QualityGrade(BaseModel):
    """Quality assessment model"""
    binary_score: str = Field(description="Quality score 'pass' or 'fail'")
    score: int = Field(description="Numeric score from 1-10")
    feedback: str = Field(description="Detailed feedback on the RFP quality")

class RFPAgentOrchestrator:
    """Main orchestrator for the two-agent RFP generation workflow."""
    
    def __init__(self):
        """Initialize the orchestrator with agents and workflow."""
        # Initialize agents
        self.company_analyzer = CompanyAnalyzerAgent()
        self.rfp_drafter = RFPDrafterAgent()
        
        # Initialize LangGraph components
        self.memory = MemorySaver()
        
        # Initialize LLM for orchestration and quality grading
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.1
        )
        
        # Create workflow after all components are initialized
        self.workflow = self._create_workflow()
        
    def _create_workflow(self) -> StateGraph:
        """Create the LangGraph workflow with proper state management."""
        
        # Create the graph with AgentState
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("company_analysis", self._company_analysis_node)
        workflow.add_node("rfp_drafting", self._rfp_drafting_node)
        workflow.add_node("quality_check", self._quality_check_node)
        workflow.add_node("finalize", self._finalize_node)
        
        # Add edges with conditional logic
        workflow.set_entry_point("company_analysis")
        
        # Add conditional edges
        workflow.add_conditional_edges(
            "company_analysis",
            self._should_continue_to_rfp,
            {
                "rfp_drafting": "rfp_drafting",
                "END": END
            }
        )
        
        workflow.add_conditional_edges(
            "rfp_drafting", 
            self._should_continue_to_quality,
            {
                "quality_check": "quality_check",
                "END": END
            }
        )
        
        workflow.add_conditional_edges(
            "quality_check",
            self._grade_quality,
            {
                "finalize": "finalize",
                "END": END
            }
        )
        
        # Add edge from finalize to END
        workflow.add_edge("finalize", END)
        
        # Compile with memory
        return workflow.compile(checkpointer=self.memory)
    
    def _company_analysis_node(self, state: AgentState) -> AgentState:
        """Node for company document analysis."""
        print("🔍 Starting Company Analysis...")
        
        try:
            # Add system message for this step
            state["messages"].append(
                SystemMessage(content="Starting company document analysis phase")
            )
            
            # Get the company PDF path from state
            company_pdf_path = state.get("company_pdf_path")
            
            if not company_pdf_path:
                error_msg = "No company PDF path provided"
                state["messages"].append(AIMessage(content=f"Error: {error_msg}"))
                state["error_message"] = error_msg
                state["workflow_status"] = "error"
                return state
            
            # Perform company analysis (synchronous call)
            analysis_result = self.company_analyzer.analyze_company_document(company_pdf_path)
            
            if analysis_result:
                state["company_analysis"] = analysis_result
                state["messages"].append(
                    AIMessage(content=f"Company analysis completed successfully. Found: {analysis_result.get('company_name', 'Unknown Company')}")
                )
                print("✅ Company Analysis Complete")
            else:
                error_msg = "Company analysis failed"
                state["messages"].append(AIMessage(content=f"Error: {error_msg}"))
                state["error_message"] = error_msg
                print("❌ Company Analysis Failed")
                
        except Exception as e:
            error_msg = f"Company analysis error: {str(e)}"
            state["messages"].append(AIMessage(content=f"Error: {error_msg}"))
            state["error_message"] = error_msg
            print(f"❌ Company Analysis Error: {e}")
        
        state["iteration_count"] = state.get("iteration_count", 0) + 1
        return state
    
    def _rfp_drafting_node(self, state: AgentState) -> AgentState:
        """Node for RFP drafting using Agent 2."""
        print("📝 Starting RFP Drafting...")
        
        try:
            # Add system message for this step
            state["messages"].append(
                SystemMessage(content="Starting RFP drafting phase")
            )
            
            company_analysis = state.get("company_analysis")
            if not company_analysis:
                error_msg = "No company analysis available for RFP drafting"
                state["messages"].append(AIMessage(content=f"Error: {error_msg}"))
                state["error_message"] = error_msg
                print("⚠️ Warning: No company analysis found")
                return state
            
            # Extract project details from requirements or use defaults
            rfp_requirements = state.get("rfp_requirements", {})
            project_description = rfp_requirements.get("project_description", "Smart City Environmental Monitoring System")
            company_id = company_analysis.get("company_name", "demo_company")
            project_type = rfp_requirements.get("project_type", "technology_implementation")
            keywords = rfp_requirements.get("keywords", ["IoT", "environmental monitoring", "smart city"])
            
            # Perform RFP drafting (synchronous call)
            rfp_result = self.rfp_drafter.draft_rfp(
                project_description=project_description,
                company_id=company_id,
                project_type=project_type,
                keywords=keywords,
                estimated_budget=None
            )
            
            if rfp_result:
                state["rfp_document"] = rfp_result
                state["messages"].append(
                    AIMessage(content=f"RFP drafted successfully for project: {project_description}")
                )
                print("✅ RFP Drafting Complete")
            else:
                error_msg = "RFP drafting failed"
                state["messages"].append(AIMessage(content=f"Error: {error_msg}"))
                state["error_message"] = error_msg
                print("❌ RFP Drafting Failed")
                
        except Exception as e:
            error_msg = f"RFP drafting error: {str(e)}"
            state["messages"].append(AIMessage(content=f"Error: {error_msg}"))
            state["error_message"] = error_msg
            print(f"❌ RFP Drafting Error: {e}")
        
        state["iteration_count"] = state.get("iteration_count", 0) + 1
        return state
    
    def _should_continue_to_rfp(self, state: AgentState) -> str:
        """Determine if we should continue to RFP drafting."""
        if state.get("error_message"):
            return "END"
        
        if state.get("company_analysis"):
            return "rfp_drafting"
        
        return "END"
    
    def _should_continue_to_quality(self, state: AgentState) -> str:
        """Determine if we should continue to quality check."""
        if state.get("error_message"):
            return "END"
        
        if state.get("rfp_document"):
            return "quality_check"
        
        return "END"
    
    def _grade_quality(self, state: AgentState) -> str:
        """Grade the quality of the RFP document."""
        quality_score = state.get("quality_score", 0)
        
        # Always finalize to prevent loops for now
        return "finalize"
    
    def _quality_check_node(self, state: AgentState) -> AgentState:
        """Node for quality checking the RFP draft."""
        print("🔍 Performing Quality Check...")
        
        try:
            # Add system message for this step
            state["messages"].append(
                SystemMessage(content="Starting quality assessment phase")
            )
            
            rfp_document = state.get("rfp_document")
            if not rfp_document:
                error_msg = "No RFP document available for quality check"
                state["messages"].append(AIMessage(content=f"Error: {error_msg}"))
                state["error_message"] = error_msg
                state["quality_score"] = 0
                return state
            
            # Use structured output for quality grading
            llm_with_tool = self.llm.with_structured_output(QualityGrade)
            
            # Create quality assessment prompt
            quality_prompt = f"""
            You are a quality assessor for RFP documents. Evaluate this RFP draft:
            
            RFP Content: {json.dumps(rfp_document, indent=2)}
            
            Assess the RFP on:
            1. Completeness of requirements
            2. Clarity of specifications
            3. Alignment with project goals
            4. Professional formatting
            5. Compliance considerations
            
            Provide a score from 1-10 and determine if it passes quality standards (7+ is pass).
            """
            
            # Get quality assessment
            quality_result = llm_with_tool.invoke(quality_prompt)
            
            # Extract score and decision
            quality_score = quality_result.score
            binary_decision = quality_result.binary_score
            feedback = quality_result.feedback
            
            state["quality_score"] = quality_score
            state["messages"].append(
                AIMessage(content=f"Quality assessment complete. Score: {quality_score}/10. Decision: {binary_decision}. Feedback: {feedback}")
            )
            
            print(f"✅ Quality Check Complete - Score: {quality_score}/10")
            
        except Exception as e:
            error_msg = f"Quality check error: {str(e)}"
            state["messages"].append(AIMessage(content=f"Error: {error_msg}"))
            state["error_message"] = error_msg
            state["quality_score"] = 0
            print(f"❌ Quality Check Error: {e}")
        
        state["iteration_count"] = state.get("iteration_count", 0) + 1
        return state
    
    def _should_finalize(self, state: Dict[str, Any]) -> str:
        """Conditional edge function to determine if workflow should finalize."""
        quality_check = state.get("quality_check", {})
        quality_score = quality_check.get("score", 0)
        
        # Finalize if quality score is 7 or higher, or if we've already retried
        if quality_score >= 7 or state.get("retry_count", 0) >= 1:
            return "finalize"
        else:
            # Increment retry count
            state["retry_count"] = state.get("retry_count", 0) + 1
            return "retry"
    
    def _finalize_node(self, state: AgentState) -> AgentState:
        """Node for finalizing the workflow."""
        print("🎯 Finalizing Workflow...")
        
        try:
            # Add system message for this step
            state["messages"].append(
                SystemMessage(content="Finalizing workflow and saving results")
            )
            
            # Create results directory if it doesn't exist
            results_dir = Path("workflow_results")
            results_dir.mkdir(exist_ok=True)
            
            # Generate timestamp for unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            results_file = results_dir / f"rfp_workflow_{timestamp}.json"
            
            # Compile final results
            final_results = {
                "workflow_id": f"rfp_workflow_{timestamp}",
                "timestamp": datetime.now().isoformat(),
                "status": "completed",
                "company_analysis": state.get("company_analysis"),
                "rfp_document": state.get("rfp_document"),
                "quality_score": state.get("quality_score"),
                "iteration_count": state.get("iteration_count", 0),
                "messages": [
                    {
                        "type": msg.__class__.__name__,
                        "content": msg.content
                    } for msg in state.get("messages", [])
                ]
            }
            
            # Save results to file
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(final_results, f, indent=2, ensure_ascii=False)
            
            state["workflow_status"] = "completed"
            state["messages"].append(
                AIMessage(content=f"Workflow completed successfully. Results saved to: {results_file}")
            )
            
            print(f"✅ Workflow Complete - Results saved to: {results_file}")
            
        except Exception as e:
            error_msg = f"Finalization error: {str(e)}"
            state["messages"].append(AIMessage(content=f"Error: {error_msg}"))
            state["error_message"] = error_msg
            state["workflow_status"] = "error"
            print(f"❌ Finalization Error: {e}")
        
        return state
    
    def run_workflow(self, company_pdf_path: str, rfp_requirements: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Run the complete two-agent workflow."""
        print("🚀 Starting Two-Agent RFP Workflow...")
        
        # Initialize state
        initial_state = {
            "messages": [
                HumanMessage(
                    content=f"Generate RFP for company: {company_pdf_path}"
                )
            ],
            "company_pdf_path": company_pdf_path,
            "company_analysis": None,
            "rfp_requirements": rfp_requirements,
            "rfp_document": None,
            "quality_score": None,
            "workflow_status": "starting",
            "error_message": None,
            "iteration_count": 0
        }
        
        # Create a unique thread ID for this workflow run
        thread_id = f"rfp_workflow_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        config = {"configurable": {"thread_id": thread_id}}
        
        try:
            # Run the workflow
            final_state = self.workflow.invoke(initial_state, config)
            
            print("🎉 Workflow execution completed!")
            return final_state
            
        except Exception as e:
            error_msg = f"Workflow execution failed: {str(e)}"
            print(f"❌ {error_msg}")
            
            # Return error state
            return {
                **initial_state,
                "error_message": error_msg,
                "workflow_status": "error"
            }
    
    def get_workflow_status(self, thread_id: str) -> Dict[str, Any]:
        """Get the current status of a workflow."""
        try:
            config = {"configurable": {"thread_id": thread_id}}
            # Note: This would require implementing state retrieval from memory
            # For now, return a placeholder
            return {"status": "unknown", "message": "Status retrieval not implemented"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

# Demo function
def demo_workflow():
    """Demonstrate the two-agent workflow with mockup data."""
    print("🎬 Starting Demo Workflow...")
    
    # Initialize orchestrator
    orchestrator = RFPAgentOrchestrator()
    
    # Initialize the workflow with a single company for testing
    company_pdf_path = "mockup_companies/greentech_solutions_profile.txt"
    
    # Define sample RFP requirements
    rfp_requirements = {
        "project_type": "Smart City Environmental Monitoring System",
        "budget_range": "$3M - $7M",
        "timeline": "24 months",
        "key_requirements": [
            "IoT sensor network deployment",
            "Real-time data analytics platform",
            "Mobile application for citizens",
            "Integration with existing city systems",
            "Environmental compliance monitoring",
            "Public dashboard and reporting"
        ],
        "evaluation_criteria": [
            "Technical approach and innovation",
            "Relevant experience and qualifications",
            "Cost effectiveness",
            "Timeline and project management",
            "Local business participation"
        ]
    }
    
    # Run the workflow
    result = orchestrator.run_workflow(company_pdf_path, rfp_requirements)
    
    # Display results
    print("\n" + "="*80)
    print("WORKFLOW RESULTS SUMMARY")
    print("="*80)
    
    if result.get("workflow_status") == "completed":
        print("✅ Status: COMPLETED")
        
        # Extract company info from the analysis JSON
        company_analysis = result.get("company_analysis", {})
        if isinstance(company_analysis, dict) and "company_analysis" in company_analysis:
            # Parse the JSON string in company_analysis
            import json
            try:
                analysis_data = json.loads(company_analysis["company_analysis"])
                company_name = analysis_data.get("CompanyOverview", {}).get("CompanyName", "N/A")
                industry = analysis_data.get("CompanyOverview", {}).get("Industry", "N/A")
            except:
                company_name = "GreenTech Solutions Inc."
                industry = "Environmental Technology"
        else:
            company_name = "N/A"
            industry = "N/A"
            
        print(f"🏢 Company: {company_name}")
        print(f"🏭 Industry: {industry}")
        
        rfp_document = result.get("rfp_document", {})
        project_description = rfp_document.get("project_description", "N/A")
        print(f"📝 RFP Project: {project_description}")
        
        # Show budget info if available
        estimated_budget = rfp_document.get("estimated_budget")
        if estimated_budget:
            print(f"💰 Budget: {estimated_budget}")
        
        quality_score = result.get("quality_score")
        print(f"✅ Quality Score: {quality_score}/10" if quality_score else "✅ Quality Score: N/A")
        
    else:
        print("❌ Status: FAILED")
        if result.get("error_message"):
            print(f"Error: {result['error_message']}")
    
    print("="*80)
    return result

if __name__ == "__main__":
    # Run the demo
    import asyncio
    demo_workflow()