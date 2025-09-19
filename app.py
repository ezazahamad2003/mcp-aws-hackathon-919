#!/usr/bin/env python3
"""
ChicoX Backend API
Flask application that connects the frontend with the existing agent orchestrator system.
Provides endpoints for company analysis and RFP generation.
"""

import os
import sys
import json
import tempfile
from datetime import datetime
from typing import Dict, Any, Optional
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import uuid

# Add the current directory to Python path to import our agents
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent_company_analyzer import CompanyAnalyzerAgent
from agent_rfp_drafter import RFPDrafterAgent
from agent_orchestrator import RFPAgentOrchestrator

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend communication

# Configuration
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'temp_uploads'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'doc', 'docx'}

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize agents
try:
    company_analyzer = CompanyAnalyzerAgent()
    rfp_drafter = RFPDrafterAgent()
    orchestrator = RFPAgentOrchestrator()
    print("✅ All agents initialized successfully")
except Exception as e:
    print(f"❌ Error initializing agents: {e}")
    company_analyzer = None
    rfp_drafter = None
    orchestrator = None

def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_file(file_path: str, filename: str) -> str:
    """Extract text content from uploaded file."""
    try:
        # For now, handle only text files
        # In production, you'd want to add PDF, DOC parsing
        if filename.lower().endswith('.txt'):
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            # For demo purposes, return placeholder for other file types
            return f"Content extracted from {filename} (placeholder for PDF/DOC parsing)"
    except Exception as e:
        print(f"Error extracting text from {filename}: {e}")
        return ""

@app.route('/')
def index():
    """Serve the frontend."""
    return send_from_directory('frontend', 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    """Serve static files from frontend directory."""
    return send_from_directory('frontend', filename)

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'agents_available': {
            'company_analyzer': company_analyzer is not None,
            'rfp_drafter': rfp_drafter is not None,
            'orchestrator': orchestrator is not None
        }
    })

@app.route('/api/analyze-company', methods=['POST'])
def analyze_company():
    """Analyze company profile from uploaded content."""
    try:
        data = request.get_json()
        
        if not data or 'content' not in data:
            return jsonify({'error': 'No content provided'}), 400
        
        filename = data.get('filename', 'company_profile.txt')
        content = data.get('content', '')
        
        if not content.strip():
            return jsonify({'error': 'Empty content provided'}), 400
        
        # Save content to temporary file for processing
        company_id = f"temp_{uuid.uuid4().hex[:8]}"
        temp_file = os.path.join(app.config['UPLOAD_FOLDER'], f"{company_id}.txt")
        
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        if company_analyzer:
            # Use the actual company analyzer
            print(f"📊 Analyzing company profile: {filename}")
            analysis_result = company_analyzer.analyze_company_profile(temp_file, company_id)
            
            if 'error' in analysis_result:
                return jsonify({'error': analysis_result['error']}), 500
            
            # Extract relevant information for frontend
            analysis_data = analysis_result.get('analysis', {})
            
            # Parse the analysis content to extract structured data
            response_data = parse_company_analysis(analysis_data, content)
            
        else:
            # Fallback to mock data if agents not available
            response_data = create_mock_analysis_from_content(content)
        
        # Clean up temporary file
        try:
            os.remove(temp_file)
        except:
            pass
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"❌ Error in analyze_company: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate-rfp', methods=['POST'])
def generate_rfp():
    """Generate RFP document based on project requirements and company analysis."""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        project_description = data.get('project_description', '')
        project_type = data.get('project_type', 'general')
        estimated_budget = data.get('estimated_budget')
        keywords = data.get('keywords', [])
        company_analysis = data.get('company_analysis', {})
        
        if not project_description.strip():
            return jsonify({'error': 'Project description is required'}), 400
        
        if orchestrator:
            # Use the actual orchestrator
            print(f"🚀 Generating RFP for project: {project_description[:50]}...")
            
            # Create a temporary company file for this session
            company_id = f"session_{uuid.uuid4().hex[:8]}"
            temp_file = os.path.join(app.config['UPLOAD_FOLDER'], f"{company_id}.txt")
            
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(f"Project Description: {project_description}\n")
                f.write(f"Project Type: {project_type}\n")
                f.write(f"Keywords: {', '.join(keywords)}\n")
                if estimated_budget:
                    f.write(f"Estimated Budget: ${estimated_budget:,.0f}\n")
                if company_analysis:
                    f.write(f"\nCompany Analysis:\n{json.dumps(company_analysis, indent=2)}\n")
            
            # Create RFP requirements dictionary
            rfp_requirements = {
                'project_description': project_description,
                'project_type': project_type,
                'estimated_budget': estimated_budget,
                'keywords': keywords,
                'company_analysis': company_analysis
            }
            
            # Run the workflow with the temporary file
            workflow_result = orchestrator.run_workflow(
                company_pdf_path=temp_file,
                rfp_requirements=rfp_requirements
            )
            
            if 'error' in workflow_result:
                return jsonify({'error': workflow_result['error']}), 500
            
            # Extract RFP content from workflow result
            rfp_content = extract_rfp_from_workflow(workflow_result)
            quality_score = workflow_result.get('quality_score', 'N/A')
            
            response_data = {
                'title': extract_title_from_description(project_description),
                'content': rfp_content,
                'quality_score': f"{quality_score}/10" if quality_score != 'N/A' else 'N/A',
                'workflow_id': workflow_result.get('workflow_status'),
                'timestamp': datetime.now().isoformat()
            }
            
            # Clean up temporary file
            try:
                os.remove(temp_file)
            except:
                pass
            
        else:
            # Fallback to mock RFP generation
            response_data = create_mock_rfp(project_description, project_type, estimated_budget)
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"❌ Error in generate_rfp: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/regenerate-rfp', methods=['POST'])
def regenerate_rfp():
    """Regenerate RFP with feedback."""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        original_rfp = data.get('original_rfp', {})
        feedback = data.get('feedback', '')
        
        if not feedback.strip():
            return jsonify({'error': 'Feedback is required'}), 400
        
        # For now, simulate regeneration by modifying the original
        # In production, you'd want to call the orchestrator with feedback
        
        response_data = original_rfp.copy()
        response_data['content'] = f"{original_rfp.get('content', '')}\n\n[UPDATED BASED ON FEEDBACK: {feedback}]"
        response_data['timestamp'] = datetime.now().isoformat()
        response_data['feedback_applied'] = feedback
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"❌ Error in regenerate_rfp: {e}")
        return jsonify({'error': str(e)}), 500

def parse_company_analysis(analysis_data: Dict[str, Any], content: str) -> Dict[str, Any]:
    """Parse company analysis data for frontend consumption."""
    try:
        # Extract company information from the analysis
        # This is a simplified parser - in production you'd want more robust parsing
        
        company_name = "Unknown Company"
        industry = "Not specified"
        employees = "Not specified"
        revenue = "Not specified"
        capabilities = []
        certifications = []
        
        # Try to extract from content if analysis doesn't have structured data
        lines = content.upper().split('\n')
        
        for i, line in enumerate(lines):
            if 'COMPANY NAME:' in line:
                company_name = line.split(':', 1)[1].strip()
            elif 'INDUSTRY:' in line:
                industry = line.split(':', 1)[1].strip()
            elif 'EMPLOYEES:' in line:
                employees = line.split(':', 1)[1].strip()
            elif 'REVENUE:' in line or 'ANNUAL REVENUE:' in line:
                revenue = line.split(':', 1)[1].strip()
            elif 'PRIMARY SERVICES:' in line or 'CORE CAPABILITIES:' in line:
                # Extract capabilities from following lines
                for j in range(i+1, min(i+10, len(lines))):
                    if lines[j].strip().startswith('•') or lines[j].strip().startswith('-'):
                        cap = lines[j].strip().lstrip('•-').strip()
                        if cap:
                            capabilities.append(cap)
            elif 'CERTIFICATIONS' in line:
                # Extract certifications from following lines
                for j in range(i+1, min(i+15, len(lines))):
                    if lines[j].strip().startswith('•') or lines[j].strip().startswith('-'):
                        cert = lines[j].strip().lstrip('•-').strip()
                        if cert:
                            certifications.append(cert)
        
        return {
            'company_name': company_name,
            'industry': industry,
            'employees': employees,
            'revenue': revenue,
            'capabilities': capabilities[:10],  # Limit to first 10
            'bonding_capacity': 'Not specified',
            'credit_rating': 'Not specified',
            'insurance': 'Not specified',
            'certifications': certifications[:10]  # Limit to first 10
        }
        
    except Exception as e:
        print(f"Error parsing company analysis: {e}")
        return create_mock_analysis_from_content(content)

def create_mock_analysis_from_content(content: str) -> Dict[str, Any]:
    """Create mock analysis data from content."""
    return {
        'company_name': 'Analyzed Company',
        'industry': 'Technology Services',
        'employees': 'Not specified',
        'revenue': 'Not specified',
        'capabilities': [
            'Technology Solutions',
            'Project Management',
            'System Integration',
            'Consulting Services'
        ],
        'bonding_capacity': 'Not specified',
        'credit_rating': 'Not specified',
        'insurance': 'Standard coverage',
        'certifications': [
            'Industry Standard Certifications',
            'Quality Management Systems'
        ]
    }

def extract_rfp_from_workflow(workflow_result: Dict[str, Any]) -> str:
    """Extract RFP content from workflow result."""
    try:
        # Try to get RFP content from different possible locations
        rfp_data = workflow_result.get('rfp_document', {})
        
        if isinstance(rfp_data, dict):
            return rfp_data.get('rfp_content', 'RFP content not available')
        elif isinstance(rfp_data, str):
            return rfp_data
        else:
            return 'RFP content not available'
            
    except Exception as e:
        print(f"Error extracting RFP content: {e}")
        return 'Error extracting RFP content'

def extract_title_from_description(description: str) -> str:
    """Extract a title from project description."""
    # Simple title extraction - take first sentence or first 50 chars
    sentences = description.split('.')
    if sentences:
        title = sentences[0].strip()
        if len(title) > 50:
            title = title[:47] + "..."
        return title
    return "Generated RFP Document"

def create_mock_rfp(project_description: str, project_type: str, estimated_budget: Optional[float]) -> Dict[str, Any]:
    """Create mock RFP data for demo purposes."""
    title = extract_title_from_description(project_description)
    budget_text = f"${estimated_budget:,.0f}" if estimated_budget else "To be determined"
    
    content = f"""REQUEST FOR PROPOSAL
{title.upper()}

PROJECT OVERVIEW
{project_description}

BUDGET AND FINANCIAL REQUIREMENTS
Estimated Budget: {budget_text}
Contract Duration: 12-24 months
Payment Terms: Net 30 days

TECHNICAL REQUIREMENTS
- Comprehensive solution design and implementation
- Integration with existing systems
- Performance monitoring and reporting
- Documentation and training
- Ongoing support and maintenance

VENDOR QUALIFICATIONS
- Minimum 3 years experience in {project_type} projects
- Relevant certifications and licenses
- Financial stability and bonding capacity
- Local presence preferred
- Strong references from similar projects

EVALUATION CRITERIA
- Technical approach and methodology (40%)
- Cost proposal and value (30%)
- Company qualifications and experience (20%)
- Project timeline and deliverables (10%)

SUBMISSION REQUIREMENTS
Proposals must be submitted by [DATE] and include:
- Executive summary
- Technical proposal and approach
- Detailed cost breakdown
- Company qualifications and references
- Project timeline and milestones
- Risk management plan

CONTACT INFORMATION
For questions regarding this RFP, please contact:
Email: procurement@chicox.gov
Phone: (555) 123-4567

Submission Deadline: [DATE]
Expected Award Date: [DATE]
Project Start Date: [DATE]"""

    return {
        'title': title,
        'content': content,
        'quality_score': '8/10',
        'timestamp': datetime.now().isoformat()
    }

if __name__ == '__main__':
    print("🚀 Starting ChicoX Backend API...")
    print("📁 Frontend available at: http://localhost:5000")
    print("🔗 API endpoints available at: http://localhost:5000/api/")
    
    # Run in debug mode for development
    app.run(debug=True, host='0.0.0.0', port=5000)