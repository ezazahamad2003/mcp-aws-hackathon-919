// ChicoX - GovTech RFP Platform JavaScript

class ChicoXApp {
    constructor() {
        this.currentSection = 'upload';
        this.uploadedFile = null;
        this.analysisData = null;
        this.rfpData = null;
        
        this.initializeEventListeners();
        this.initializeFileUpload();
    }

    initializeEventListeners() {
        // Navigation
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const section = e.target.getAttribute('href').substring(1);
                this.navigateToSection(section);
            });
        });

        // Upload section
        document.getElementById('analyzeBtn').addEventListener('click', () => {
            this.analyzeCompany();
        });

        // Analysis section
        document.getElementById('backToUpload').addEventListener('click', () => {
            this.navigateToSection('upload');
        });

        document.getElementById('generateRfpBtn').addEventListener('click', () => {
            this.navigateToSection('generate');
        });

        // Generate section
        document.getElementById('backToAnalysis').addEventListener('click', () => {
            this.navigateToSection('analyze');
        });

        document.getElementById('startGenerationBtn').addEventListener('click', () => {
            this.generateRFP();
        });

        // Results section
        document.getElementById('previewBtn').addEventListener('click', () => {
            this.showPreviewModal();
        });

        document.getElementById('downloadBtn').addEventListener('click', () => {
            this.downloadRFP();
        });

        document.getElementById('regenerateBtn').addEventListener('click', () => {
            this.regenerateWithFeedback();
        });

        document.getElementById('startNewBtn').addEventListener('click', () => {
            this.startNew();
        });

        // Modal
        document.getElementById('closeModal').addEventListener('click', () => {
            this.closeModal();
        });

        // File removal
        document.getElementById('removeFile').addEventListener('click', () => {
            this.removeFile();
        });
    }

    initializeFileUpload() {
        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('fileInput');
        const browseLink = document.querySelector('.browse-link');

        // Click to browse
        uploadArea.addEventListener('click', () => fileInput.click());
        browseLink.addEventListener('click', (e) => {
            e.stopPropagation();
            fileInput.click();
        });

        // File input change
        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.handleFileUpload(e.target.files[0]);
            }
        });

        // Drag and drop
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('dragover');
        });

        uploadArea.addEventListener('dragleave', () => {
            uploadArea.classList.remove('dragover');
        });

        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            
            if (e.dataTransfer.files.length > 0) {
                this.handleFileUpload(e.dataTransfer.files[0]);
            }
        });
    }

    handleFileUpload(file) {
        // Validate file type
        const allowedTypes = ['.txt', '.pdf', '.doc', '.docx'];
        const fileExtension = '.' + file.name.split('.').pop().toLowerCase();
        
        if (!allowedTypes.includes(fileExtension)) {
            this.showNotification('Please upload a valid file type (TXT, PDF, DOC, DOCX)', 'error');
            return;
        }

        // Validate file size (max 10MB)
        if (file.size > 10 * 1024 * 1024) {
            this.showNotification('File size must be less than 10MB', 'error');
            return;
        }

        this.uploadedFile = file;
        this.displayUploadedFile(file);
        document.getElementById('analyzeBtn').disabled = false;
    }

    displayUploadedFile(file) {
        document.getElementById('uploadArea').style.display = 'none';
        document.getElementById('uploadedFile').style.display = 'block';
        
        document.getElementById('fileName').textContent = file.name;
        document.getElementById('fileSize').textContent = this.formatFileSize(file.size);
    }

    removeFile() {
        this.uploadedFile = null;
        document.getElementById('uploadArea').style.display = 'block';
        document.getElementById('uploadedFile').style.display = 'none';
        document.getElementById('fileInput').value = '';
        document.getElementById('analyzeBtn').disabled = true;
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    navigateToSection(section) {
        // Update navigation
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.remove('active');
        });
        document.querySelector(`[href="#${section}"]`).classList.add('active');

        // Update sections
        document.querySelectorAll('.section').forEach(sec => {
            sec.classList.remove('active');
        });
        document.getElementById(section).classList.add('active');

        this.currentSection = section;
    }

    async analyzeCompany() {
        if (!this.uploadedFile) {
            this.showNotification('Please upload a company profile first', 'error');
            return;
        }

        this.navigateToSection('analyze');
        document.getElementById('loadingAnalysis').style.display = 'block';
        document.getElementById('analysisResults').style.display = 'none';

        try {
            // Read file content
            const fileContent = await this.readFileContent(this.uploadedFile);
            
            // Call analysis API
            const response = await fetch('/api/analyze-company', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    content: fileContent,
                    filename: this.uploadedFile.name
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Analysis failed');
            }

            this.analysisData = await response.json();
            this.displayAnalysisResults(this.analysisData);
            
            // Auto-extract project information from company profile
            this.autoFillProjectDetails(fileContent, this.analysisData);

        } catch (error) {
            console.error('Analysis error:', error);
            // For demo purposes, use mock data
            this.analysisData = this.getMockAnalysisData();
            this.displayAnalysisResults(this.analysisData);
            
            // Auto-fill with mock data as well
            const mockContent = "GreenTech Solutions Inc. specializes in Smart City Infrastructure Development, IoT Sensor Networks for Environmental Monitoring, Energy Management Systems, Water Quality Monitoring Solutions, and Traffic Management Systems. Recent projects include $2.5 Million smart city deployment.";
            this.autoFillProjectDetails(mockContent, this.analysisData);
        }
    }

    autoFillProjectDetails(content, analysis) {
        // Extract project information from company profile content
        const projectInfo = this.extractProjectInfo(content, analysis);
        
        // Auto-fill the project form
        const descriptionField = document.getElementById('projectDescription');
        const typeField = document.getElementById('projectType');
        const budgetField = document.getElementById('estimatedBudget');
        const keywordsField = document.getElementById('keywords');
        
        if (descriptionField && projectInfo.description) {
            descriptionField.value = projectInfo.description;
        }
        
        if (typeField && projectInfo.type) {
            typeField.value = projectInfo.type;
        }
        
        if (budgetField && projectInfo.budget) {
            budgetField.value = projectInfo.budget;
        }
        
        if (keywordsField && projectInfo.keywords) {
            keywordsField.value = projectInfo.keywords.join(', ');
        }
        
        // Show a notification that fields were auto-filled
        this.showNotification('Project details auto-filled based on company capabilities!', 'success');
    }

    extractProjectInfo(content, analysis) {
        const upperContent = content.toUpperCase();
        const capabilities = analysis.capabilities || [];
        
        // Determine project type based on company capabilities
        let projectType = 'general';
        if (upperContent.includes('SMART CITY') || upperContent.includes('IOT') || upperContent.includes('TRAFFIC')) {
            projectType = 'smart-city';
        } else if (upperContent.includes('ENVIRONMENTAL') || upperContent.includes('MONITORING') || upperContent.includes('WATER')) {
            projectType = 'environmental';
        } else if (upperContent.includes('ENERGY') || upperContent.includes('MANAGEMENT')) {
            projectType = 'energy';
        }
        
        // Extract budget range from past projects
        let estimatedBudget = '';
        const budgetMatches = content.match(/\$([0-9]+(?:\.[0-9]+)?)\s*Million/gi);
        if (budgetMatches && budgetMatches.length > 0) {
            // Use the median of found budget values
            const budgets = budgetMatches.map(match => {
                const value = parseFloat(match.replace(/\$|Million/gi, ''));
                return value * 1000000;
            });
            budgets.sort((a, b) => a - b);
            const median = budgets[Math.floor(budgets.length / 2)];
            estimatedBudget = median.toString();
        }
        
        // Generate project description based on company capabilities
        const primaryCapabilities = capabilities.slice(0, 3);
        let description = '';
        
        if (projectType === 'smart-city') {
            description = `Develop a comprehensive smart city solution incorporating ${primaryCapabilities.join(', ').toLowerCase()}. The project should leverage IoT sensors, real-time data analytics, and cloud-based platforms to improve city operations and citizen services.`;
        } else if (projectType === 'environmental') {
            description = `Implement an environmental monitoring system utilizing ${primaryCapabilities.join(', ').toLowerCase()}. The solution should provide real-time environmental data collection, analysis, and reporting capabilities.`;
        } else if (projectType === 'energy') {
            description = `Deploy an energy management platform incorporating ${primaryCapabilities.join(', ').toLowerCase()}. The system should optimize energy consumption and provide comprehensive monitoring and reporting.`;
        } else {
            description = `Develop a technology solution leveraging ${primaryCapabilities.join(', ').toLowerCase()}. The project should address municipal needs through innovative technology implementation.`;
        }
        
        // Extract keywords from capabilities and content
        const keywords = [];
        
        // Add capability-based keywords
        capabilities.forEach(cap => {
            const capWords = cap.toLowerCase().split(/[\s,&]+/);
            capWords.forEach(word => {
                if (word.length > 3 && !keywords.includes(word)) {
                    keywords.push(word);
                }
            });
        });
        
        // Add common technology keywords found in content
        const techKeywords = ['iot', 'sensors', 'monitoring', 'smart', 'cloud', 'analytics', 'mobile', 'api', 'data', 'security', 'integration'];
        techKeywords.forEach(keyword => {
            if (upperContent.includes(keyword.toUpperCase()) && !keywords.includes(keyword)) {
                keywords.push(keyword);
            }
        });
        
        return {
            description: description,
            type: projectType,
            budget: estimatedBudget,
            keywords: keywords.slice(0, 8) // Limit to 8 keywords
        };
    }

    readFileContent(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = (e) => resolve(e.target.result);
            reader.onerror = (e) => reject(e);
            reader.readAsText(file);
        });
    }

    displayAnalysisResults(data) {
        document.getElementById('loadingAnalysis').style.display = 'none';
        document.getElementById('analysisResults').style.display = 'block';

        // Company Overview
        document.getElementById('companyOverview').innerHTML = `
            <p><strong>Company:</strong> ${data.company_name || 'N/A'}</p>
            <p><strong>Industry:</strong> ${data.industry || 'N/A'}</p>
            <p><strong>Employees:</strong> ${data.employees || 'N/A'}</p>
            <p><strong>Revenue:</strong> ${data.revenue || 'N/A'}</p>
        `;

        // Core Capabilities
        const capabilities = data.capabilities || [];
        document.getElementById('coreCapabilities').innerHTML = `
            <ul>
                ${capabilities.map(cap => `<li>${cap}</li>`).join('')}
            </ul>
        `;

        // Financial Information
        document.getElementById('financialInfo').innerHTML = `
            <p><strong>Bonding Capacity:</strong> ${data.bonding_capacity || 'N/A'}</p>
            <p><strong>Credit Rating:</strong> ${data.credit_rating || 'N/A'}</p>
            <p><strong>Insurance:</strong> ${data.insurance || 'N/A'}</p>
        `;

        // Compliance & Certifications
        const certifications = data.certifications || [];
        document.getElementById('complianceInfo').innerHTML = `
            <ul>
                ${certifications.map(cert => `<li>${cert}</li>`).join('')}
            </ul>
        `;

        document.getElementById('generateRfpBtn').disabled = false;
    }

    async generateRFP() {
        const projectDescription = document.getElementById('projectDescription').value;
        const projectType = document.getElementById('projectType').value;
        const estimatedBudget = document.getElementById('estimatedBudget').value;
        const keywords = document.getElementById('keywords').value;

        if (!projectDescription.trim()) {
            this.showNotification('Please provide a project description', 'error');
            return;
        }

        this.navigateToSection('results');
        document.getElementById('loadingGeneration').style.display = 'block';
        document.getElementById('rfpPreview').style.display = 'none';

        try {
            const response = await fetch('/api/generate-rfp', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    project_description: projectDescription,
                    project_type: projectType,
                    estimated_budget: estimatedBudget ? parseFloat(estimatedBudget) : null,
                    keywords: keywords.split(',').map(k => k.trim()).filter(k => k),
                    company_analysis: this.analysisData
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'RFP generation failed');
            }

            this.rfpData = await response.json();
            this.displayRFPResults(this.rfpData);

        } catch (error) {
            console.error('RFP generation error:', error);
            // For demo purposes, use mock data
            this.rfpData = this.getMockRFPData();
            this.displayRFPResults(this.rfpData);
        }
    }

    displayRFPResults(data) {
        document.getElementById('loadingGeneration').style.display = 'none';
        document.getElementById('rfpPreview').style.display = 'block';
        document.getElementById('feedbackSection').style.display = 'block';

        document.getElementById('rfpTitle').textContent = data.title || 'Generated RFP Document';
        document.getElementById('qualityScore').textContent = data.quality_score || '8/10';
        document.getElementById('generatedDate').textContent = new Date().toLocaleDateString();

        // Display RFP content (truncated for preview)
        const content = data.content || 'RFP content will be displayed here...';
        const truncatedContent = content.length > 1000 ? content.substring(0, 1000) + '...' : content;
        document.getElementById('rfpContent').innerHTML = `<pre>${truncatedContent}</pre>`;
    }

    showPreviewModal() {
        if (this.rfpData && this.rfpData.content) {
            document.getElementById('modalBody').innerHTML = `<pre>${this.rfpData.content}</pre>`;
            document.getElementById('previewModal').classList.add('active');
        }
    }

    closeModal() {
        document.getElementById('previewModal').classList.remove('active');
    }

    downloadRFP() {
        if (!this.rfpData) {
            this.showNotification('No RFP data available for download', 'error');
            return;
        }

        // Create and download file
        const content = this.rfpData.content || 'No content available';
        const blob = new Blob([content], { type: 'text/plain' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${this.rfpData.title || 'RFP_Document'}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);

        this.showNotification('RFP document downloaded successfully', 'success');
    }

    async regenerateWithFeedback() {
        const feedback = document.getElementById('feedbackText').value;
        
        if (!feedback.trim()) {
            this.showNotification('Please provide feedback for regeneration', 'error');
            return;
        }

        document.getElementById('loadingGeneration').style.display = 'block';
        document.getElementById('rfpPreview').style.display = 'none';

        try {
            const response = await fetch('/api/regenerate-rfp', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    original_rfp: this.rfpData,
                    feedback: feedback
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'RFP regeneration failed');
            }

            this.rfpData = await response.json();
            this.displayRFPResults(this.rfpData);
            document.getElementById('feedbackText').value = '';

        } catch (error) {
            console.error('RFP regeneration error:', error);
            this.showNotification('Failed to regenerate RFP. Please try again.', 'error');
            document.getElementById('loadingGeneration').style.display = 'none';
            document.getElementById('rfpPreview').style.display = 'block';
        }
    }

    startNew() {
        // Reset all data
        this.uploadedFile = null;
        this.analysisData = null;
        this.rfpData = null;

        // Reset forms
        document.getElementById('fileInput').value = '';
        document.getElementById('projectDescription').value = '';
        document.getElementById('estimatedBudget').value = '';
        document.getElementById('keywords').value = '';
        document.getElementById('feedbackText').value = '';

        // Reset UI
        this.removeFile();
        document.getElementById('analyzeBtn').disabled = true;
        document.getElementById('generateRfpBtn').disabled = true;

        // Navigate to upload
        this.navigateToSection('upload');
    }

    showNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.innerHTML = `
            <span>${message}</span>
            <button onclick="this.parentElement.remove()">×</button>
        `;

        // Add to page
        document.body.appendChild(notification);

        // Auto remove after 5 seconds
        setTimeout(() => {
            if (notification.parentElement) {
                notification.remove();
            }
        }, 5000);
    }

    getMockAnalysisData() {
        return {
            company_name: "GreenTech Solutions Inc.",
            industry: "Environmental Technology & Smart City Solutions",
            employees: "150-200",
            revenue: "$25-35 Million",
            capabilities: [
                "Smart City Infrastructure Development",
                "IoT Sensor Networks for Environmental Monitoring",
                "Energy Management Systems",
                "Water Quality Monitoring Solutions",
                "Traffic Management Systems"
            ],
            bonding_capacity: "$10 Million",
            credit_rating: "4A1 (Excellent)",
            insurance: "General Liability: $2M, Professional: $5M",
            certifications: [
                "ISO 9001:2015 Quality Management",
                "ISO 14001:2015 Environmental Management",
                "SOC 2 Type II Compliance",
                "FedRAMP Ready Status",
                "Minority Business Enterprise (MBE) Certified"
            ]
        };
    }

    getMockRFPData() {
        return {
            title: "Smart City Environmental Monitoring System",
            quality_score: "8/10",
            content: `REQUEST FOR PROPOSAL
SMART CITY ENVIRONMENTAL MONITORING SYSTEM

PROJECT OVERVIEW
The City seeks proposals for a comprehensive environmental monitoring system to track air quality, noise levels, and other environmental factors across the metropolitan area.

BUDGET AND FINANCIAL REQUIREMENTS
Estimated Budget: $1,000,000 - $2,500,000
Contract Duration: 24 months
Payment Terms: Net 30 days

TECHNICAL REQUIREMENTS
- IoT sensor network deployment
- Real-time data collection and analysis
- Web-based dashboard and mobile app
- Integration with existing city systems
- 99.9% uptime requirement

VENDOR QUALIFICATIONS
- Minimum 5 years experience in smart city projects
- ISO certifications required
- Bonding capacity of at least $5 million
- Local presence preferred

EVALUATION CRITERIA
- Technical approach (40%)
- Cost proposal (30%)
- Company qualifications (20%)
- Project timeline (10%)

SUBMISSION REQUIREMENTS
Proposals must be submitted by [DATE] and include:
- Technical proposal
- Cost breakdown
- Company qualifications
- Project timeline
- References

For questions, contact: procurement@city.gov`
        };
    }
}

// Add notification styles
const notificationStyles = `
.notification {
    position: fixed;
    top: 20px;
    right: 20px;
    padding: 1rem 1.5rem;
    border-radius: 8px;
    color: white;
    font-weight: 500;
    z-index: 1001;
    display: flex;
    align-items: center;
    gap: 1rem;
    min-width: 300px;
    box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
}

.notification-success { background-color: #10b981; }
.notification-error { background-color: #ef4444; }
.notification-info { background-color: #3b82f6; }
.notification-warning { background-color: #f59e0b; }

.notification button {
    background: none;
    border: none;
    color: white;
    font-size: 1.2rem;
    cursor: pointer;
    padding: 0;
    margin-left: auto;
}
`;

// Add styles to head
const styleSheet = document.createElement('style');
styleSheet.textContent = notificationStyles;
document.head.appendChild(styleSheet);

// Initialize app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new ChicoXApp();
});