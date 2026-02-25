"""
Veda 4.0 - Phase 2 Week 2: SAP Landscape Analyzer

Intelligent analysis layer for SAP landscapes.
Provides insights, recommendations, and automated health checks.

PURPOSE:
- Analyze landscape health and performance
- Generate optimization recommendations
- Identify risks and issues
- Provide capacity planning insights
- Best practice validation

LAYERS:
- knowledge_service.py: Data retrieval (what exists)
- landscape_analyzer.py: Intelligence (what it means) ← YOU ARE HERE
- orchestrator.py: User interaction (how to communicate)

USAGE:
    from src.sap.landscape_analyzer import LandscapeAnalyzer
    
    # Initialize
    analyzer = LandscapeAnalyzer(knowledge_service)
    
    # Run comprehensive analysis
    analysis = analyzer.analyze_landscape()
    
    # Get specific insights
    risks = analyzer.identify_risks()
    recommendations = analyzer.get_recommendations()
    capacity = analyzer.analyze_capacity()
    
    # Generate report
    report = analyzer.generate_analysis_report()
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import structlog

logger = structlog.get_logger()


class RiskLevel(Enum):
    """Risk severity levels."""
    CRITICAL = "CRITICAL"  # Immediate action required
    HIGH = "HIGH"          # Action required soon
    MEDIUM = "MEDIUM"      # Should be addressed
    LOW = "LOW"            # Nice to fix
    INFO = "INFO"          # Informational only


class RecommendationType(Enum):
    """Types of recommendations."""
    PERFORMANCE = "PERFORMANCE"
    SECURITY = "SECURITY"
    AVAILABILITY = "AVAILABILITY"
    COST = "COST"
    COMPLIANCE = "COMPLIANCE"
    BEST_PRACTICE = "BEST_PRACTICE"


@dataclass
class Risk:
    """Identified risk in the landscape."""
    risk_id: str
    level: RiskLevel
    category: str
    title: str
    description: str
    affected_entities: List[str] = field(default_factory=list)
    impact: str = ""
    mitigation: str = ""
    
    def __str__(self) -> str:
        return f"[{self.level.value}] {self.title}: {self.description}"


@dataclass
class Recommendation:
    """Optimization recommendation."""
    recommendation_id: str
    type: RecommendationType
    priority: int  # 1-10 (10 = highest)
    title: str
    description: str
    benefit: str
    effort: str  # LOW, MEDIUM, HIGH
    affected_entities: List[str] = field(default_factory=list)
    
    def __str__(self) -> str:
        return f"[P{self.priority}] {self.title} (Effort: {self.effort})"


@dataclass
class CapacityInsight:
    """Capacity and sizing insight."""
    metric: str
    current_value: float
    threshold: float
    status: str  # OK, WARNING, CRITICAL
    recommendation: str = ""
    
    @property
    def utilization_percent(self) -> float:
        """Calculate utilization percentage."""
        if self.threshold == 0:
            return 0.0
        return (self.current_value / self.threshold) * 100
    
    def __str__(self) -> str:
        return f"{self.metric}: {self.current_value}/{self.threshold} ({self.utilization_percent:.1f}%) - {self.status}"


@dataclass
class LandscapeAnalysis:
    """Complete landscape analysis results."""
    project_id: str
    analyzed_at: datetime
    health_score: float  # 0.0-1.0
    risk_score: float    # 0.0-1.0 (higher = more risk)
    risks: List[Risk]
    recommendations: List[Recommendation]
    capacity_insights: List[CapacityInsight]
    summary: Dict[str, Any]
    
    @property
    def critical_risks_count(self) -> int:
        """Count critical risks."""
        return sum(1 for r in self.risks if r.level == RiskLevel.CRITICAL)
    
    @property
    def high_priority_recommendations_count(self) -> int:
        """Count high priority recommendations (>= 8)."""
        return sum(1 for r in self.recommendations if r.priority >= 8)
    
    def __str__(self) -> str:
        return (
            f"Landscape Analysis | "
            f"Health: {self.health_score:.2f} | "
            f"Risks: {len(self.risks)} ({self.critical_risks_count} critical) | "
            f"Recommendations: {len(self.recommendations)}"
        )


class LandscapeAnalyzer:
    """
    Intelligent SAP landscape analyzer.
    
    Provides analysis, insights, and recommendations based on
    data retrieved from knowledge_service.py.
    """
    
    def __init__(self, knowledge_service):
        """
        Initialize landscape analyzer.
        
        Args:
            knowledge_service: SAPKnowledgeService instance
        """
        self.knowledge_service = knowledge_service
        self.project_id = knowledge_service.project_id
        
        logger.info(
            "landscape_analyzer_initialized",
            project_id=self.project_id
        )
    
    # =========================================================================
    # RISK IDENTIFICATION
    # =========================================================================
    
    def identify_risks(self) -> List[Risk]:
        """
        Identify risks in the landscape.
        
        Returns:
            List of Risk objects
        """
        risks = []
        
        # Get data from knowledge service
        health = self.knowledge_service.get_landscape_health()
        systems = self.knowledge_service.get_all_systems()
        instances = self.knowledge_service.get_all_instances()
        
        # Risk 1: Port conflicts (CRITICAL)
        if health.port_conflicts:
            risks.append(Risk(
                risk_id="PORT_CONFLICTS",
                level=RiskLevel.CRITICAL,
                category="availability",
                title="Port Conflicts Detected",
                description=f"Found {len(health.port_conflicts)} port conflicts that will prevent instances from starting",
                affected_entities=[
                    f"{c.instance1.get('sid')}_{c.instance1.get('instance_number')}"
                    for c in health.port_conflicts[:5]
                ],
                impact="Instances cannot start, system unavailability",
                mitigation="Reassign instance numbers to avoid port collisions"
            ))
        
        # Risk 2: Missing dependencies (HIGH)
        critical_deps = [d for d in health.missing_dependencies if d.is_critical]
        if critical_deps:
            risks.append(Risk(
                risk_id="MISSING_DEPENDENCIES",
                level=RiskLevel.HIGH,
                category="availability",
                title="Critical Dependency Violations",
                description=f"Found {len(critical_deps)} critical dependency violations",
                impact="Startup failures, unpredictable behavior",
                mitigation="Review and fix dependency chain"
            ))
        
        # Risk 3: No production systems (HIGH)
        prod_systems = [s for s in systems if s.get('landscape_tier') == 'PRD']
        if not prod_systems and len(systems) > 0:
            risks.append(Risk(
                risk_id="NO_PRODUCTION",
                level=RiskLevel.HIGH,
                category="compliance",
                title="No Production Systems Defined",
                description="Landscape has no systems marked as PRD tier",
                impact="No production environment for business operations",
                mitigation="Define and configure production systems"
            ))
        
        # Risk 4: Single point of failure (MEDIUM)
        # Check for single ASCS instance per system
        for system in systems:
            system_instances = [
                i for i in instances 
                if i.get('sid') == system.get('sid')
            ]
            ascs_instances = [
                i for i in system_instances 
                if i.get('instance_type') == 'ASCS'
            ]
            
            if len(ascs_instances) == 1 and system.get('landscape_tier') == 'PRD':
                risks.append(Risk(
                    risk_id=f"SPOF_{system.get('sid')}",
                    level=RiskLevel.MEDIUM,
                    category="availability",
                    title=f"Single Point of Failure in {system.get('sid')}",
                    description="Production system has no ERS (Enqueue Replication Server)",
                    affected_entities=[system.get('sid')],
                    impact="System downtime if ASCS fails",
                    mitigation="Implement ERS for high availability"
                ))
        
        # Risk 5: Validation errors (varies by severity)
        if health.validation_errors:
            error_count = len(health.validation_errors)
            level = RiskLevel.HIGH if error_count > 5 else RiskLevel.MEDIUM
            
            risks.append(Risk(
                risk_id="VALIDATION_ERRORS",
                level=level,
                category="data_quality",
                title="Landscape Validation Errors",
                description=f"Found {error_count} validation errors",
                impact="Data quality issues, potential operational problems",
                mitigation="Review and fix validation errors"
            ))
        
        # Risk 6: Low health score (varies)
        if health.health_score < 0.6:
            level = RiskLevel.CRITICAL if health.health_score < 0.4 else RiskLevel.HIGH
            risks.append(Risk(
                risk_id="LOW_HEALTH_SCORE",
                level=level,
                category="overall",
                title="Poor Landscape Health",
                description=f"Overall health score is {health.health_score:.2f}",
                impact="Multiple issues affecting landscape reliability",
                mitigation="Address identified risks and recommendations"
            ))
        
        logger.info(
            "risks_identified",
            total_risks=len(risks),
            critical=sum(1 for r in risks if r.level == RiskLevel.CRITICAL),
            high=sum(1 for r in risks if r.level == RiskLevel.HIGH)
        )
        
        return risks
    
    # =========================================================================
    # RECOMMENDATIONS
    # =========================================================================
    
    def get_recommendations(self) -> List[Recommendation]:
        """
        Generate optimization recommendations.
        
        Returns:
            List of Recommendation objects
        """
        recommendations = []
        
        systems = self.knowledge_service.get_all_systems()
        instances = self.knowledge_service.get_all_instances()
        health = self.knowledge_service.get_landscape_health()
        
        # Recommendation 1: Implement HA for production (HIGH PRIORITY)
        prod_systems = [s for s in systems if s.get('landscape_tier') == 'PRD']
        for system in prod_systems:
            system_instances = [
                i for i in instances 
                if i.get('sid') == system.get('sid')
            ]
            has_ers = any(i.get('instance_type') == 'ERS' for i in system_instances)
            
            if not has_ers:
                recommendations.append(Recommendation(
                    recommendation_id=f"HA_{system.get('sid')}",
                    type=RecommendationType.AVAILABILITY,
                    priority=9,
                    title=f"Implement High Availability for {system.get('sid')}",
                    description="Add ERS (Enqueue Replication Server) for failover protection",
                    benefit="99.9% uptime, automatic failover, no single point of failure",
                    effort="MEDIUM",
                    affected_entities=[system.get('sid')]
                ))
        
        # Recommendation 2: Fix port conflicts (CRITICAL)
        if health.port_conflicts:
            recommendations.append(Recommendation(
                recommendation_id="FIX_PORT_CONFLICTS",
                type=RecommendationType.AVAILABILITY,
                priority=10,
                title="Resolve Port Conflicts",
                description=f"Fix {len(health.port_conflicts)} port conflicts",
                benefit="Enable all instances to start successfully",
                effort="LOW",
                affected_entities=[
                    f"{c.instance1.get('sid')}" 
                    for c in health.port_conflicts[:5]
                ]
            ))
        
        # Recommendation 3: Standardize instance numbers (BEST PRACTICE)
        # Check if instance numbers follow convention
        ascs_with_wrong_number = [
            i for i in instances
            if i.get('instance_type') == 'ASCS' and i.get('instance_number') != '00'
        ]
        
        if ascs_with_wrong_number:
            recommendations.append(Recommendation(
                recommendation_id="STANDARDIZE_INSTANCE_NUMBERS",
                type=RecommendationType.BEST_PRACTICE,
                priority=5,
                title="Standardize Instance Numbering",
                description="ASCS instances should use instance number 00 by convention",
                benefit="Easier troubleshooting, follows SAP best practices",
                effort="MEDIUM",
                affected_entities=[i.get('sid') for i in ascs_with_wrong_number]
            ))
        
        # Recommendation 4: Add multiple app servers (PERFORMANCE)
        for system in systems:
            system_instances = [
                i for i in instances 
                if i.get('sid') == system.get('sid')
            ]
            app_servers = [
                i for i in system_instances 
                if i.get('instance_type') in ['PAS', 'AAS']
            ]
            
            if len(app_servers) == 1 and system.get('landscape_tier') == 'PRD':
                recommendations.append(Recommendation(
                    recommendation_id=f"ADD_AAS_{system.get('sid')}",
                    type=RecommendationType.PERFORMANCE,
                    priority=7,
                    title=f"Add Application Servers to {system.get('sid')}",
                    description="Single app server limits scalability and creates bottleneck",
                    benefit="Load balancing, better performance, increased capacity",
                    effort="MEDIUM",
                    affected_entities=[system.get('sid')]
                ))
        
        # Recommendation 5: Document missing information (DATA QUALITY)
        incomplete_systems = [
            s for s in systems 
            if not s.get('description') or not s.get('kernel_version')
        ]
        
        if incomplete_systems and len(incomplete_systems) > len(systems) * 0.3:
            recommendations.append(Recommendation(
                recommendation_id="COMPLETE_DOCUMENTATION",
                type=RecommendationType.BEST_PRACTICE,
                priority=4,
                title="Complete System Documentation",
                description=f"{len(incomplete_systems)} systems missing key information",
                benefit="Better landscape visibility and management",
                effort="LOW",
                affected_entities=[s.get('sid') for s in incomplete_systems[:5]]
            ))
        
        # Recommendation 6: Implement monitoring (BEST PRACTICE)
        # This is always recommended if landscape has production systems
        if prod_systems:
            recommendations.append(Recommendation(
                recommendation_id="IMPLEMENT_MONITORING",
                type=RecommendationType.AVAILABILITY,
                priority=8,
                title="Implement Comprehensive Monitoring",
                description="Set up automated monitoring for all production systems",
                benefit="Early problem detection, reduced downtime, proactive management",
                effort="MEDIUM",
                affected_entities=[s.get('sid') for s in prod_systems]
            ))
        
        # Sort by priority (highest first)
        recommendations.sort(key=lambda r: r.priority, reverse=True)
        
        logger.info(
            "recommendations_generated",
            total=len(recommendations),
            high_priority=sum(1 for r in recommendations if r.priority >= 8)
        )
        
        return recommendations
    
    # =========================================================================
    # CAPACITY ANALYSIS
    # =========================================================================
    
    def analyze_capacity(self) -> List[CapacityInsight]:
        """
        Analyze landscape capacity and sizing.
        
        Returns:
            List of CapacityInsight objects
        """
        insights = []
        
        systems = self.knowledge_service.get_all_systems()
        instances = self.knowledge_service.get_all_instances()
        hosts = self.knowledge_service.get_hosts()
        
        # Insight 1: System count
        # Typical small landscape: 3-5 systems
        # Typical medium: 6-15 systems
        # Typical large: 16+ systems
        system_count = len(systems)
        if system_count < 10:
            threshold = 10
            status = "OK"
        elif system_count < 20:
            threshold = 20
            status = "OK"
        else:
            threshold = 30
            status = "WARNING" if system_count > 25 else "OK"
        
        insights.append(CapacityInsight(
            metric="Total Systems",
            current_value=system_count,
            threshold=threshold,
            status=status,
            recommendation="Consider landscape consolidation if >30 systems" if system_count > 20 else ""
        ))
        
        # Insight 2: Instances per system (avg)
        if systems:
            avg_instances = len(instances) / len(systems)
            # Typical: 3-5 instances per system (ASCS, PAS, 1-2 AAS, HDB)
            threshold = 5.0
            status = "OK" if avg_instances <= 6 else "WARNING"
            
            insights.append(CapacityInsight(
                metric="Avg Instances per System",
                current_value=avg_instances,
                threshold=threshold,
                status=status,
                recommendation="Review instance distribution" if avg_instances > 6 else ""
            ))
        
        # Insight 3: Production system ratio
        prod_count = sum(1 for s in systems if s.get('landscape_tier') == 'PRD')
        if systems:
            prod_ratio = prod_count / len(systems)
            # Typical: 20-30% production systems
            threshold = 0.3
            status = "OK" if 0.2 <= prod_ratio <= 0.4 else "WARNING"
            
            insights.append(CapacityInsight(
                metric="Production System Ratio",
                current_value=prod_ratio,
                threshold=threshold,
                status=status,
                recommendation="Maintain 20-40% production systems" if status == "WARNING" else ""
            ))
        
        # Insight 4: Host utilization
        if hosts and instances:
            instances_per_host = {}
            for instance in instances:
                hostname = instance.get('hostname', 'unknown')
                instances_per_host[hostname] = instances_per_host.get(hostname, 0) + 1
            
            if instances_per_host:
                avg_per_host = sum(instances_per_host.values()) / len(instances_per_host)
                # Typical: 2-4 instances per host
                threshold = 4.0
                status = "OK" if avg_per_host <= 5 else "WARNING"
                
                insights.append(CapacityInsight(
                    metric="Avg Instances per Host",
                    current_value=avg_per_host,
                    threshold=threshold,
                    status=status,
                    recommendation="Consider adding hosts" if avg_per_host > 5 else ""
                ))
        
        logger.info(
            "capacity_analyzed",
            insights_count=len(insights),
            warnings=sum(1 for i in insights if i.status == "WARNING")
        )
        
        return insights
    
    # =========================================================================
    # COMPREHENSIVE ANALYSIS
    # =========================================================================
    
    def analyze_landscape(self) -> LandscapeAnalysis:
        """
        Perform comprehensive landscape analysis.
        
        Returns:
            LandscapeAnalysis object with all insights
        """
        logger.info("comprehensive_analysis_started", project_id=self.project_id)
        
        # Gather all insights
        health = self.knowledge_service.get_landscape_health()
        risks = self.identify_risks()
        recommendations = self.get_recommendations()
        capacity_insights = self.analyze_capacity()
        stats = self.knowledge_service.get_statistics()
        
        # Calculate risk score (0.0 = no risk, 1.0 = maximum risk)
        risk_score = 0.0
        risk_score += sum(0.3 for r in risks if r.level == RiskLevel.CRITICAL)
        risk_score += sum(0.2 for r in risks if r.level == RiskLevel.HIGH)
        risk_score += sum(0.1 for r in risks if r.level == RiskLevel.MEDIUM)
        risk_score += sum(0.05 for r in risks if r.level == RiskLevel.LOW)
        risk_score = min(1.0, risk_score)  # Cap at 1.0
        
        # Create summary
        summary = {
            "total_systems": stats['total_systems'],
            "total_instances": stats['total_instances'],
            "total_hosts": stats['total_hosts'],
            "health_score": health.health_score,
            "risk_score": risk_score,
            "critical_risks": sum(1 for r in risks if r.level == RiskLevel.CRITICAL),
            "high_priority_recommendations": sum(1 for r in recommendations if r.priority >= 8),
            "capacity_warnings": sum(1 for i in capacity_insights if i.status == "WARNING"),
            "analyzed_at": datetime.now().isoformat()
        }
        
        analysis = LandscapeAnalysis(
            project_id=self.project_id,
            analyzed_at=datetime.now(),
            health_score=health.health_score,
            risk_score=risk_score,
            risks=risks,
            recommendations=recommendations,
            capacity_insights=capacity_insights,
            summary=summary
        )
        
        logger.info(
            "comprehensive_analysis_complete",
            health_score=health.health_score,
            risk_score=risk_score,
            risks=len(risks),
            recommendations=len(recommendations)
        )
        
        return analysis
    
    # =========================================================================
    # REPORTING
    # =========================================================================
    
    def generate_analysis_report(self) -> str:
        """
        Generate human-readable analysis report.
        
        Returns:
            Formatted report string
        """
        analysis = self.analyze_landscape()
        
        report = []
        report.append("=" * 80)
        report.append(f"SAP LANDSCAPE ANALYSIS REPORT - {self.project_id}")
        report.append("=" * 80)
        report.append(f"Generated: {analysis.analyzed_at.strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        
        # Executive Summary
        report.append("EXECUTIVE SUMMARY")
        report.append("-" * 80)
        report.append(str(analysis))
        report.append("")
        
        # Health & Risk Scores
        report.append("SCORES")
        report.append("-" * 80)
        health_status = "✅ HEALTHY" if analysis.health_score >= 0.8 else "⚠️  NEEDS ATTENTION"
        risk_status = "✅ LOW RISK" if analysis.risk_score < 0.3 else "⚠️  ELEVATED RISK"
        report.append(f"Health Score: {analysis.health_score:.2f}/1.00 - {health_status}")
        report.append(f"Risk Score:   {analysis.risk_score:.2f}/1.00 - {risk_status}")
        report.append("")
        
        # Critical Risks
        critical_risks = [r for r in analysis.risks if r.level == RiskLevel.CRITICAL]
        if critical_risks:
            report.append("CRITICAL RISKS (IMMEDIATE ACTION REQUIRED)")
            report.append("-" * 80)
            for risk in critical_risks:
                report.append(f"❌ {risk.title}")
                report.append(f"   {risk.description}")
                report.append(f"   Impact: {risk.impact}")
                report.append(f"   Mitigation: {risk.mitigation}")
                report.append("")
        
        # Top Recommendations
        top_recommendations = [r for r in analysis.recommendations if r.priority >= 8]
        if top_recommendations:
            report.append("TOP RECOMMENDATIONS (HIGH PRIORITY)")
            report.append("-" * 80)
            for rec in top_recommendations[:5]:
                report.append(f"⭐ [P{rec.priority}] {rec.title}")
                report.append(f"   {rec.description}")
                report.append(f"   Benefit: {rec.benefit}")
                report.append(f"   Effort: {rec.effort}")
                report.append("")
        
        # Capacity Insights
        capacity_warnings = [i for i in analysis.capacity_insights if i.status == "WARNING"]
        if capacity_warnings:
            report.append("CAPACITY WARNINGS")
            report.append("-" * 80)
            for insight in capacity_warnings:
                report.append(f"⚠️  {insight}")
                if insight.recommendation:
                    report.append(f"   Recommendation: {insight.recommendation}")
                report.append("")
        
        # All Risks Summary
        if analysis.risks:
            report.append("ALL IDENTIFIED RISKS")
            report.append("-" * 80)
            for level in [RiskLevel.CRITICAL, RiskLevel.HIGH, RiskLevel.MEDIUM, RiskLevel.LOW]:
                level_risks = [r for r in analysis.risks if r.level == level]
                if level_risks:
                    report.append(f"{level.value}: {len(level_risks)} risk(s)")
            report.append("")
        
        report.append("=" * 80)
        report.append("END OF REPORT")
        report.append("=" * 80)
        
        return "\n".join(report)


# Convenience function
def create_analyzer(knowledge_service) -> LandscapeAnalyzer:
    """
    Create landscape analyzer instance.
    
    Args:
        knowledge_service: SAPKnowledgeService instance
    
    Returns:
        LandscapeAnalyzer instance
    """
    return LandscapeAnalyzer(knowledge_service)
