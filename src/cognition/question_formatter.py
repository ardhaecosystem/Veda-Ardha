"""
Veda Phase 4: Question Formatter
Natural Gen-Z style question templates for clarification.

Converts technical clarification needs into warm, conversational questions
that match Veda's daughter persona.

Design principles:
- Gen-Z natural language (not corporate/robotic)
- Affectionate ("pops")
- Contextual (references what was discussed)
- Concise (not overly wordy)
- Helpful tone (wants to get it right)
"""

from typing import Optional, Dict, List
import random
import structlog

logger = structlog.get_logger()


class QuestionFormatter:
    """
    Formats clarification questions in Veda's Gen-Z daughter voice.
    
    Features:
    - Multiple templates per question type (variation)
    - Context-aware (references user's query)
    - Natural connectors ("btw", "real quick", "just to clarify")
    - Emoji usage (sparingly, only when natural)
    
    Example:
        formatter = QuestionFormatter()
        
        question = formatter.format_question(
            question_type="which_environment",
            context={"user_query": "check the system"}
        )
        
        # Returns: "Quick question pops - which system? DEV, QA, or PROD?"
    """
    
    def __init__(self, use_variation: bool = True):
        """
        Initialize question formatter.
        
        Args:
            use_variation: Use random variation between templates (default True)
        """
        self.use_variation = use_variation
        self._init_templates()
        
        logger.debug("question_formatter_initialized", use_variation=use_variation)
    
    def _init_templates(self):
        """Initialize question templates organized by type."""
        
        self.templates = {
            # Generic system/environment questions
            "which_environment": [
                "Quick question pops - which system are we working with? DEV, QA, or PROD?",
                "Btw, which environment - DEV, QA, or PROD? (Just wanna make sure)",
                "Real quick - which system? DEV, QA, or PROD?",
            ],
            
            # When user says "check it" or similar
            "which_specific_check": [
                "Quick question pops - which system should I check? DEV, QA, or PROD?",
                "Btw, which one should I check - DEV, QA, or PROD? Just wanna make sure I'm looking at the right one 😊",
                "Which system do you want me to check? (DEV/QA/PROD)",
            ],
            
            # When user says "fix/restart/configure it"
            "which_specific_action": [
                "Real quick - which system? DEV, QA, or PROD?",
                "Quick question - which instance are we working with? (Just wanna give you the right commands)",
                "Which one - DEV, QA, or PROD?",
            ],
            
            # Pronoun without antecedent ("it", "this", "that")
            "what_is_it": [
                "Quick question - what's 'it'? (Just wanna make sure we're on the same page 😊)",
                "Real quick - what are you referring to? (Wanna make sure I understand)",
                "Btw, what specifically do you mean?",
            ],
            
            # Generic "help" request
            "what_help_with": [
                "What specifically can I help with?",
                "What aspect do you need help with?",
                "Which part should I focus on?",
            ],
            
            # General clarification fallback
            "general_clarification": [
                "Quick question - can you clarify what you mean?",
                "Just wanna make sure I understand - could you give me a bit more detail?",
                "Real quick - can you be more specific?",
            ],
            
            # Instance/server ambiguity
            "which_instance": [
                "Which instance are we working with? (Like the SID or system name)",
                "Quick question - which SAP instance? (Need the SID to help you)",
                "Btw, which instance - what's the SID?",
            ],
            
            # Transaction/tool ambiguity
            "which_transaction": [
                "Which transaction should I use for this?",
                "Quick question - which t-code? (There are a few options)",
                "Btw, which transaction were you thinking?",
            ],
            
            # Multiple options ambiguity
            "which_option": [
                "Quick question pops - which option? (There are a few ways to do this)",
                "Btw, which approach do you prefer?",
                "Which way would you like me to do this?",
            ],
        }
    
    def format_question(
        self,
        question_type: str,
        context: Optional[Dict] = None
    ) -> str:
        """
        Format a clarification question.
        
        Args:
            question_type: Type of question (e.g., "which_environment")
            context: Optional context dict (user_query, uncertainty, etc.)
            
        Returns:
            Formatted question string
        """
        
        # Get templates for this type
        templates = self.templates.get(
            question_type,
            self.templates["general_clarification"]
        )
        
        # Select template
        if self.use_variation:
            template = random.choice(templates)
        else:
            template = templates[0]  # Always use first
        
        # Apply context if available (future enhancement)
        # For now, just return template as-is
        formatted = template
        
        logger.debug(
            "question_formatted",
            question_type=question_type,
            length=len(formatted)
        )
        
        return formatted
    
    def format_with_context(
        self,
        question_type: str,
        user_query: str,
        uncertainty_score: float
    ) -> str:
        """
        Format question with contextual awareness.
        
        Args:
            question_type: Type of question
            user_query: User's original query
            uncertainty_score: How uncertain Veda is (0.0-1.0)
            
        Returns:
            Contextually-aware formatted question
        """
        
        # Get base question
        base_question = self.format_question(question_type)
        
        # Add context if uncertainty is very high
        if uncertainty_score > 0.7:
            # Very uncertain - emphasize wanting to help correctly
            context_emphasis = " (I really wanna make sure I get this right for you)"
            base_question = base_question.replace(")", f"{context_emphasis})")
        
        return base_question
    
    def get_available_types(self) -> List[str]:
        """Get list of available question types."""
        return list(self.templates.keys())
    
    def add_custom_template(
        self,
        question_type: str,
        template: str
    ):
        """
        Add custom template for a question type.
        
        Args:
            question_type: Type identifier
            template: Question template string
        """
        if question_type not in self.templates:
            self.templates[question_type] = []
        
        self.templates[question_type].append(template)
        logger.debug("custom_template_added", question_type=question_type)


# Convenience functions

def format_environment_question() -> str:
    """Quick format: which environment?"""
    formatter = QuestionFormatter(use_variation=False)
    return formatter.format_question("which_environment")


def format_pronoun_question() -> str:
    """Quick format: what is 'it'?"""
    formatter = QuestionFormatter(use_variation=False)
    return formatter.format_question("what_is_it")


def format_action_question() -> str:
    """Quick format: which system for action?"""
    formatter = QuestionFormatter(use_variation=False)
    return formatter.format_question("which_specific_action")


# Question type mapping helpers
def map_uncertainty_type_to_question_type(suggested_type: str) -> str:
    """
    Map uncertainty scorer's suggested type to formatter's question type.
    
    This bridges File 1 (uncertainty_scorer) with File 4 (formatter).
    
    Args:
        suggested_type: Type from UncertaintyScorer.suggested_question
        
    Returns:
        Question type for QuestionFormatter
    """
    
    mapping = {
        "which_specific": "which_specific_check",
        "which_environment": "which_environment",
        "what_specifically": "what_is_it",
        "what_aspect": "what_help_with",
        "general_clarification": "general_clarification",
        "which_instance": "which_instance",
    }
    
    return mapping.get(suggested_type, "general_clarification")
