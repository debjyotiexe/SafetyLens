#!/usr/bin/env python3
"""
SafetyLens AI Project Report Generator
Run this script to generate a comprehensive Word document report.

Requirements: pip install python-docx
"""

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
import os

def create_report():
    """Generate the SafetyLens AI project report."""
    
    doc = Document()
    
    # Title
    title = doc.add_heading('SafetyLens AI: Real-Time PPE Compliance Monitoring Platform', 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    subtitle = doc.add_paragraph('A Comprehensive Project Report')
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.runs[0].font.size = Pt(14)
    subtitle.runs[0].font.color.rgb = RGBColor(100, 100, 100)
    
    doc.add_paragraph()
    
    # Executive Summary
    doc.add_heading('Executive Summary', 1)
    doc.add_paragraph(
        'SafetyLens AI is an enterprise-grade computer vision platform designed to automate workplace safety compliance '
        'monitoring. Leveraging custom-trained YOLOv8 models, real-time video processing, and intelligent alerting systems, '
        'the platform detects Personal Protective Equipment (PPE) violations across multiple camera feeds and provides '
        'actionable insights to safety managers. The system processes video streams at native resolution, applies geometric '
        'compliance rules with temporal confirmation, and maintains comprehensive incident logs with automated alerts via '
        'email and webhooks.'
    )
    
    doc.add_page_break()
    
    # Problem Statement
    doc.add_heading('1. Problem Statement', 1)
    doc.add_paragraph(
        'Construction sites and industrial facilities face significant challenges in maintaining consistent safety compliance:'
    )
    problems = [
        'Manual PPE monitoring is labor-intensive, unreliable, and cannot scale across multiple camera feeds',
        'Workers frequently bypass safety protocols when not under direct supervision',
        'Accident prevention relies on reactive measures rather than proactive detection',
        'Traditional CCTV systems lack intelligence to identify specific safety violations',
        'Safety managers lack real-time visibility into compliance across large facilities',
        'Incident documentation is often incomplete, delayed, or inaccurate'
    ]
    for problem in problems:
        doc.add_paragraph(problem, style='List Bullet')
    
    doc.add_paragraph(
        '\nThese challenges result in preventable workplace injuries, regulatory violations, insurance liabilities, '
        'and operational inefficiencies that cost industries billions annually.'
    )
    
    # Solution Overview
    doc.add_heading('2. Solution Overview', 1)
    doc.add_paragraph(
        'SafetyLens AI addresses these challenges through an intelligent, automated monitoring platform that:'
    )
    solutions = [
        'Detects PPE compliance violations in real-time using custom-trained computer vision models',
        'Processes multiple video streams concurrently (webcams, RTSP cameras, video files)',
        'Applies geometric compliance rules with temporal confirmation to eliminate false positives',
        'Maintains comprehensive incident logs with snapshot evidence',
        'Provides real-time alerting via email and webhook integrations',
        'Offers an industrial-grade command center dashboard for monitoring and incident management'
    ]
    for solution in solutions:
        doc.add_paragraph(solution, style='List Bullet')
    
    doc.add_page_break()
    
    # Technical Architecture
    doc.add_heading('3. Technical Architecture', 1)
    
    doc.add_heading('3.1 System Components', 2)
    doc.add_paragraph(
        'The platform follows a modular, microservices-inspired architecture with clear separation of concerns:'
    )
    
    arch_table = doc.add_table(rows=1, cols=3)
    arch_table.style = 'Light Grid Accent 1'
    hdr_cells = arch_table.rows[0].cells
    hdr_cells[0].text = 'Layer'
    hdr_cells[1].text = 'Technology'
    hdr_cells[2].text = 'Responsibility'
    
    arch_data = [
        ('Frontend', 'HTML5, CSS3, Vanilla JavaScript', 'Industrial HUD dashboard, real-time video display, incident management UI'),
        ('Backend API', 'Python 3.11, FastAPI', 'REST API, WebSocket streaming, authentication, settings management'),
        ('Computer Vision', 'YOLOv8, Ultralytics, OpenCV', 'Real-time object detection, PPE classification, geometric compliance'),
        ('Video Processing', 'OpenCV, Threading', 'Multi-camera stream ingestion, frame decoding, snapshot caching'),
        ('Database', 'SQLite (local) / PostgreSQL (planned)', 'Incident logs, camera configurations, user management'),
        ('Alerting', 'smtplib, httpx', 'Email notifications, webhook integrations, log handlers'),
        ('Deployment', 'Docker, Docker Compose, GitHub Actions', 'Containerization, CI/CD pipeline, automated testing')
    ]
    
    for layer, tech, resp in arch_data:
        row_cells = arch_table.add_row().cells
        row_cells[0].text = layer
        row_cells[1].text = tech
        row_cells[2].text = resp
    
    doc.add_heading('3.2 Data Flow Pipeline', 2)
    doc.add_paragraph('The end-to-end processing pipeline:')
    pipeline_steps = [
        'Video frame acquisition (WebSocket from browser / RTSP stream / local file)',
        'Frame decoding and preprocessing via OpenCV',
        'YOLOv8 inference with custom-trained model at native resolution',
        'Detection extraction: Person bounding boxes + PPE items (helmet, vest, gloves, boots, goggles)',
        'Geometric compliance checking using person-relative body zones',
        'Temporal confirmation (3-frame rule) to eliminate flickering detections',
        'Violation logging with snapshot evidence capture',
        'Real-time alert dispatch (email/webhook/log) via thread pool',
        'WebSocket response with annotated frame and violation metadata',
        'Incident management and CSV export for safety manager review'
    ]
    for i, step in enumerate(pipeline_steps, 1):
        doc.add_paragraph(f'{i}. {step}', style='List Number')
    
    doc.add_page_break()
    
    # Implementation Details
    doc.add_heading('4. Implementation Details', 1)
    
    doc.add_heading('4.1 Custom YOLOv8 Model Training', 2)
    doc.add_paragraph(
        'The AI/ML Engineer trained a custom YOLOv8n model on the Construction-PPE and Roboflow datasets, achieving:'
    )
    model_metrics = [
        'Person detection: 91.3% mAP50, 92.5% recall',
        'Helmet detection: 82.6% mAP50, 82.1% recall',
        'Vest detection: 85.6% mAP50, 83.0% recall',
        'Gloves detection: 81.3% mAP50, 80.1% recall',
        'Boots detection: 78.9% mAP50, 79.8% recall',
        'Goggles detection: 81.1% mAP50, 72.3% recall'
    ]
    for metric in model_metrics:
        doc.add_paragraph(metric, style='List Bullet')
    
    doc.add_paragraph(
        '\nTraining employed early stopping (patience=15 epochs), optimized for the RTX 4060 GPU with CUDA acceleration, '
        'resulting in inference speeds of ~1.6ms per image (600+ FPS capability).'
    )
    
    doc.add_heading('4.2 Geometric Compliance Engine', 2)
    doc.add_paragraph('The Backend Developer implemented a sophisticated compliance engine that:')
    compliance_features = [
        'Maps PPE detections to person-specific body zones (head, torso, hands, feet, eyes)',
        'Uses IoU (Intersection over Union) and center-point checks for spatial association',
        'Handles explicit negative classes (no_helmet, no_goggles, no_gloves, no_boots) with separate confidence thresholds',
        'Infers NO_VEST violations when positive vest detection is absent in torso zone',
        'Implements greedy IoU tracking for consistent person ID assignment across frames',
        'Applies 3-frame temporal confirmation to eliminate single-frame false positives',
        'Enforces 30-second cooldown per violation type to prevent alert spam'
    ]
    for feature in compliance_features:
        doc.add_paragraph(feature, style='List Bullet')
    
    doc.add_heading('4.3 Multi-Camera Manager', 2)
    doc.add_paragraph('The Camera Manager enables concurrent processing of multiple video sources:')
    camera_features = [
        'Daemon threads for each active camera (non-blocking I/O for RTSP streams)',
        'Exponential backoff retry logic for connection failures (1s to 30s)',
        'Isolated compliance state per camera (no cross-contamination)',
        'In-memory snapshot caching for low-latency thumbnail polling',
        'Dynamic camera lifecycle management (add/start/stop/delete via REST API)',
        'Graceful shutdown with thread cleanup on server termination'
    ]
    for feature in camera_features:
        doc.add_paragraph(feature, style='List Bullet')
    
    doc.add_heading('4.4 Alert Dispatcher', 2)
    doc.add_paragraph('The Alert Dispatcher provides pluggable notification handlers:')
    alert_features = [
        'ThreadPoolExecutor for non-blocking alert delivery',
        'EmailHandler: SMTP with TLS, snapshot attachment, authentication support',
        'WebhookHandler: HTTP POST with JSON payload, configurable URL',
        'LogHandler: Always-on stdout logging for audit trails',
        'Failure isolation: one handler failure does not block others',
        'Runtime configuration updates without server restart'
    ]
    for feature in alert_features:
        doc.add_paragraph(feature, style='List Bullet')
    
    doc.add_page_break()
    
    # Team Roles
    doc.add_heading('5. Team Roles & Responsibilities', 1)
    doc.add_paragraph('The project was developed collaboratively with clear role separation:')
    
    roles_table = doc.add_table(rows=1, cols=3)
    roles_table.style = 'Light Grid Accent 1'
    hdr_cells = roles_table.rows[0].cells
    hdr_cells[0].text = 'Role'
    hdr_cells[1].text = 'Owner'
    hdr_cells[2].text = 'Key Deliverables'
    
    roles_data = [
        ('Backend Developer', 'Team Member', 'FastAPI REST API, WebSocket streaming, authentication system, settings management, incident CRUD, CSV export'),
        ('AI/ML Engineer', 'Team Member', 'YOLOv8 model training, geometric compliance engine, temporal confirmation, confidence threshold tuning, model registry'),
        ('Cloud Engineer', 'Team Member', 'Docker containerization, Docker Compose orchestration, multi-camera threading, RTSP ingestion, volume persistence'),
        ('Database & UI/UX Designer', 'Team Member', 'SQLite schema design, industrial HUD design system, Cameras/Incidents/Settings pages, CSS styling'),
        ('Version Control / DevOps Engineer', 'Team Member', 'Git workflow, GitHub repository, CI/CD pipeline (GitHub Actions), automated testing (56 tests), documentation')
    ]
    
    for role, owner, deliverables in roles_data:
        row_cells = roles_table.add_row().cells
        row_cells[0].text = role
        row_cells[1].text = owner
        row_cells[2].text = deliverables
    
    # Technology Stack
    doc.add_heading('6. Technology Stack', 1)
    
    doc.add_heading('6.1 Backend Technologies', 2)
    backend_tech = [
        'Python 3.11: Core programming language',
        'FastAPI: Async web framework for REST API and WebSocket support',
        'Uvicorn: ASGI server for high-performance request handling',
        'Ultralytics YOLOv8: State-of-the-art object detection framework',
        'OpenCV: Computer vision library for frame decoding and annotation',
        'PyTorch: Deep learning backend with CUDA GPU acceleration',
        'SQLite: Lightweight relational database for local deployment',
        'aiosmtplib: Async SMTP client for email alerting',
        'httpx: Modern HTTP client for webhook integrations'
    ]
    for tech in backend_tech:
        doc.add_paragraph(tech, style='List Bullet')
    
    doc.add_heading('6.2 Frontend Technologies', 2)
    frontend_tech = [
        'HTML5: Semantic markup structure',
        'CSS3: Custom industrial HUD design system with CSS variables',
        'Vanilla JavaScript: No framework dependencies, fast load times',
        'WebSocket API: Real-time bidirectional communication',
        'Chart.js: Data visualization for analytics dashboard',
        'LocalStorage: Client-side authentication token persistence'
    ]
    for tech in frontend_tech:
        doc.add_paragraph(tech, style='List Bullet')
    
    doc.add_heading('6.3 DevOps & Infrastructure', 2)
    devops_tech = [
        'Docker: Containerization for reproducible deployments',
        'Docker Compose: Multi-container orchestration',
        'GitHub: Version control and collaboration platform',
        'GitHub Actions: CI/CD pipeline with automated testing',
        'pytest: Comprehensive test suite (56 passing tests)',
        'FFmpeg: Video codec support for diverse stream formats'
    ]
    for tech in devops_tech:
        doc.add_paragraph(tech, style='List Bullet')
    
    doc.add_page_break()
    
    # Key Features
    doc.add_heading('7. Key Features', 1)
    
    doc.add_heading('7.1 Real-Time Video Processing', 2)
    doc.add_paragraph(
        'The platform processes video streams at native resolution (1920x1080 60fps tested), applying YOLOv8 inference '
        'with ~1.6ms latency per frame. The WebSocket-based streaming ensures sub-200ms end-to-end latency from camera '
        'to dashboard display.'
    )
    
    doc.add_heading('7.2 Multi-Source Camera Support', 2)
    doc.add_paragraph('SafetyLens AI supports three camera input types:')
    camera_types = [
        'Browser WebSocket: Real-time webcam/screen capture from the dashboard',
        'RTSP streams: IP security cameras and network video sources',
        'Local files: Video files on the server filesystem for testing and review'
    ]
    for cam_type in camera_types:
        doc.add_paragraph(cam_type, style='List Bullet')
    
    doc.add_heading('7.3 Intelligent Compliance Detection', 2)
    doc.add_paragraph('The geometric compliance engine detects violations across 6 PPE categories:')
    ppe_categories = [
        'NO_HELMET: Absence of hard hat in head zone',
        'NO_VEST: Absence of safety vest in torso zone (inferred)',
        'NO_GLOVES: Absence of gloves in hand zone',
        'NO_BOOTS: Absence of safety boots in foot zone',
        'NO_GOGGLES: Absence of eye protection in eye zone',
        'Person tracking: Consistent ID assignment across frames'
    ]
    for ppe in ppe_categories:
        doc.add_paragraph(ppe, style='List Bullet')
    
    doc.add_heading('7.4 Incident Management Workflow', 2)
    doc.add_paragraph('The Incidents page provides safety managers with:')
    incident_features = [
        'Filterable table by violation type, camera, date range, and status',
        'Snapshot evidence thumbnails with full-size modal view',
        'Incident resolution workflow with admin-only permissions',
        'CSV export for compliance reporting and audit trails',
        'Real-time status updates without page refresh'
    ]
    for feature in incident_features:
        doc.add_paragraph(feature, style='List Bullet')
    
    doc.add_heading('7.5 Enterprise Alerting System', 2)
    doc.add_paragraph('Configurable alert dispatch via multiple channels:')
    alert_channels = [
        'Email alerts: SMTP integration with snapshot attachment',
        'Webhook alerts: HTTP POST to Slack, Teams, or custom endpoints',
        'Log alerts: Always-on stdout logging for audit compliance',
        'Test alerts: Verify configuration without triggering real violations'
    ]
    for channel in alert_channels:
        doc.add_paragraph(channel, style='List Bullet')
    
    doc.add_page_break()
    
    # Results & Achievements
    doc.add_heading('8. Results & Achievements', 1)
    
    doc.add_heading('8.1 Performance Metrics', 2)
    perf_metrics = [
        'Inference latency: ~1.6ms per frame (600+ FPS capability on RTX 4060)',
        'End-to-end latency: <200ms from camera to dashboard',
        'Concurrent cameras: Tested up to 4 streams at 10 FPS each',
        'Model accuracy: 82-91% mAP50 across PPE categories',
        'False positive rate: <5% with 3-frame temporal confirmation',
        'Test coverage: 56 automated tests (100% pass rate)'
    ]
    for metric in perf_metrics:
        doc.add_paragraph(metric, style='List Bullet')
    
    doc.add_heading('8.2 Development Milestones', 2)
    milestones = [
        'Phase 1: Core detection engine, single-camera WebSocket streaming, SQLite logging',
        'Phase 2: Multi-camera manager, RTSP support, alert dispatcher, incident management',
        'Sprint B: Enterprise features (cameras page, incidents page, settings page, CSV export)',
        'Hotfix Sprint: Input validation, response shape fixes, UI styling corrections'
    ]
    for milestone in milestones:
        doc.add_paragraph(milestone, style='List Bullet')
    
    doc.add_heading('8.3 Engineering Best Practices', 2)
    practices = [
        'Test-Driven Development: 56 automated tests covering compliance logic, API contracts, camera lifecycle',
        'Continuous Integration: GitHub Actions pipeline runs on every push',
        'Containerization: Docker ensures reproducible deployments across environments',
        'Modular Architecture: Clear separation of pipeline, camera manager, alert dispatcher, database layer',
        'Documentation: Comprehensive README, inline code comments, API endpoint documentation'
    ]
    for practice in practices:
        doc.add_paragraph(practice, style='List Bullet')
    
    doc.add_page_break()
    
    # Future Scope
    doc.add_heading('9. Future Scope', 1)
    doc.add_paragraph('The platform architecture supports several planned enhancements:')
    
    doc.add_heading('9.1 Cloud Deployment (Phase 3)', 2)
    cloud_features = [
        'PostgreSQL migration for production-scale incident logging',
        'Cloud storage integration (AWS S3, Google Cloud Storage) for snapshot persistence',
        'Managed database services (Supabase, AWS RDS) for high availability',
        'Cloud-hosted model registry for A/B testing and version management',
        'Load balancing for multi-region deployment'
    ]
    for feature in cloud_features:
        doc.add_paragraph(feature, style='List Bullet')
    
    doc.add_heading('9.2 Advanced Analytics (Sprint C)', 2)
    analytics_features = [
        'Compliance scoring and trend analysis',
        'Heatmaps showing violation hotspots by camera and time',
        'Worker tracking with persistent ID assignment (ByteTrack integration)',
        'Predictive analytics for proactive safety interventions',
        'Custom reporting templates for regulatory compliance'
    ]
    for feature in analytics_features:
        doc.add_paragraph(feature, style='List Bullet')
    
    doc.add_heading('9.3 Geofencing & Zone Management', 2)
    geofencing_features = [
        'Polygon-based restricted zones with customizable rules',
        'Zone-specific PPE requirements (e.g., hard hat only in Zone A)',
        'Zone entry/exit logging and dwell time tracking',
        'Visual zone overlay on camera feeds'
    ]
    for feature in geofencing_features:
        doc.add_paragraph(feature, style='List Bullet')
    
    doc.add_heading('9.4 Privacy & Security Enhancements', 2)
    privacy_features = [
        'Face blur for GDPR/privacy compliance',
        'JWT token-based authentication with refresh tokens',
        'Role-based access control (RBAC) with granular permissions',
        'Audit logging for all admin actions',
        'Encryption at rest and in transit'
    ]
    for feature in privacy_features:
        doc.add_paragraph(feature, style='List Bullet')
    
    doc.add_heading('9.5 Mobile & Edge Deployment', 2)
    mobile_features = [
        'Responsive mobile dashboard for field supervisors',
        'Edge deployment on Jetson Nano / Raspberry Pi for offline sites',
        'ONVIF camera integration for broader hardware support',
        'Native mobile apps (iOS/Android) with push notifications'
    ]
    for feature in mobile_features:
        doc.add_paragraph(feature, style='List Bullet')
    
    doc.add_page_break()
    
    # Conclusion
    doc.add_heading('10. Conclusion', 1)
    doc.add_paragraph(
        'SafetyLens AI demonstrates the successful application of modern computer vision, real-time video processing, '
        'and enterprise software architecture to solve a critical workplace safety challenge. The platform transforms '
        'passive CCTV systems into intelligent safety compliance monitors, providing real-time visibility, automated '
        'alerting, and comprehensive incident management.'
    )
    
    doc.add_paragraph('Key achievements include:')
    achievements = [
        'Custom-trained YOLOv8 model achieving 82-91% accuracy across PPE categories',
        'Geometric compliance engine with temporal confirmation eliminating false positives',
        'Multi-camera concurrent processing with isolated state management',
        'Industrial-grade command center with incident workflow and CSV export',
        'Production-ready containerization with 56 automated tests',
        'Pluggable alert system supporting email, webhook, and log channels'
    ]
    for achievement in achievements:
        doc.add_paragraph(achievement, style='List Bullet')
    
    doc.add_paragraph(
        '\nThe modular architecture and clean separation of concerns position the platform for rapid feature expansion, '
        'cloud deployment, and enterprise integration. Future sprints will add analytics, geofencing, privacy controls, '
        'and edge deployment capabilities, evolving SafetyLens AI into a comprehensive workplace safety platform.'
    )
    
    doc.add_paragraph(
        '\nSafetyLens AI represents a significant step forward in proactive safety management, potentially preventing '
        'workplace injuries, reducing regulatory violations, and providing safety managers with unprecedented visibility '
        'into compliance across their facilities.'
    )
    
    # Footer
    doc.add_paragraph()
    doc.add_paragraph()
    footer = doc.add_paragraph('---')
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer_text = doc.add_paragraph('SafetyLens AI Project Report')
    footer_text.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer_text.runs[0].font.size = Pt(10)
    footer_text.runs[0].font.color.rgb = RGBColor(128, 128, 128)
    
    footer_date = doc.add_paragraph('Generated: 2026')
    footer_date.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer_date.runs[0].font.size = Pt(10)
    footer_date.runs[0].font.color.rgb = RGBColor(128, 128, 128)
    
    # Save document
    output_path = 'SafetyLens_AI_Project_Report.docx'
    doc.save(output_path)
    
    print(f"✅ Report generated successfully!")
    print(f"📄 File: {output_path}")
    print(f"📊 Size: {os.path.getsize(output_path) / 1024:.1f} KB")
    print(f"\n💡 Open the file in Microsoft Word or Google Docs to view the formatted report!")

if __name__ == '__main__':
    create_report()