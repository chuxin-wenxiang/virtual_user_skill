#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PMF Validation Mode - Sean Ellis Disappointment Scale

Determines whether a product need truly exists by measuring user disappointment
if the feature/solution were removed.

Methodology:
  - Based on Sean Ellis' Product-Market Fit survey (2017)
  - Core question: "How disappointed would you be if this feature no longer existed?"
  - PMF Score = % "Very Disappointed" / Total Valid Responses
  - Pass threshold: >= 40%

Quality Safeguards (inspired by authentic-user v5.7):
  - Commercial viability pre-check (3 questions)
  - Prompt neutrality detection (anti-leading bias)
  - Dissenter injection (3 skeptical personas added)
  - Confidence grading (High/Medium/Low based on sample size & consistency)
"""

import math
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class PMFResponse:
    """Single user's PMF evaluation response."""
    persona_id: str
    persona_name: str
    disappointment_level: str  # 'very', 'somewhat', 'not_very', 'dont_care'
    reasoning: str
    is_dissenter: bool = False


class PMFValidationMode:
    """PMF Validation - Is this a real need?
    
    Scoring System:
      | Level | Score | Meaning |
      |-------|-------|---------|
      | Very disappointed | 3 | Solves my core pain point |
      | Somewhat disappointed | 2 | Helpful but not essential |
      | Not very disappointed | 1 | Nice to have |
      | Don't care | 0 | Irrelevant to me |
    
    PMF Score Thresholds:
      >= 80%: Extreme PMF (strong need, push forward)
      60-79%: Strong PMF (high value, prioritize)
      40-59%: Pass PMF (viable, proceed to PRD)
      < 40%: Fail (pivot or abandon)
    """
    
    DISAPPOINTMENT_SCALE = {
        'very': {'score': 3, 'label': 'Very Disappointed', 'label_cn': '非常失望'},
        'somewhat': {'score': 2, 'label': 'Somewhat Disappointed', 'label_cn': '有些失望'},
        'not_very': {'score': 1, 'label': 'Not Very Disappointed', 'label_cn': '不太失望'},
        'dont_care': {'score': 0, 'label': "Don't Care", 'label_cn': '无所谓'},
    }
    
    PMF_THRESHOLDS = [
        (0.80, 'extreme', 'Extreme PMF - Strong need, strongly recommend proceeding'),
        (0.60, 'strong', 'Strong PMF - High value, prioritize'),
        (0.40, 'pass', 'PMF Achieved - Viable, proceed to PRD'),
        (0.00, 'fail', 'PMF Not Achieved - Pivot or abandon'),
    ]
    
    def __init__(self, search_engine, user_generator):
        self.search_engine = search_engine
        self.user_generator = user_generator
    
    def run(self, question: str, sample_size: int = 20, 
            user_group: str = None, **kwargs) -> dict:
        """
        Execute PMF validation.
        
        Args:
            question: Feature/solution description
            sample_size: Target valid samples (default 20, min 8)
            user_group: Target user segment filter
        """
        sample_size = max(8, sample_size)  # Minimum 8 (Nielsen saturation point)
        
        print(f"\n[PMF Validation]")
        print(f"  Solution: {question}")
        print(f"  Target sample: {sample_size} users")
        if user_group:
            print(f"  User group: {user_group}")
        
        # Step 1: Commercial viability pre-check
        print("\n[Step 1] Commercial viability pre-check...")
        viability = self._check_commercial_viability(question)
        print(f"  Result: {viability['status']}")
        
        # Step 2: Retrieve scenarios & generate personas
        print("\n[Step 2] Generating personas...")
        scenarios = self.search_engine.search(question, top_k=sample_size * 2)
        personas = self._generate_evaluation_personas(scenarios, sample_size)
        print(f"  Generated {len(personas)} evaluation personas")
        
        # Step 3: Inject dissenter personas (3 skeptics)
        print("\n[Step 3] Injecting dissenter personas...")
        dissenters = self._generate_dissenters()
        all_personas = personas + dissenters
        print(f"  Added {len(dissenters)} dissenter personas")
        
        # Step 4: Collect responses (parallel evaluation)
        print(f"\n[Step 4] Collecting {len(all_personas)} evaluations...")
        # In production: parallel LLM calls with each persona
        responses = []  # Would be filled by LLM evaluation
        
        # Step 5: Calculate PMF Score
        print("\n[Step 5] Calculating PMF Score...")
        result = self._calculate_pmf_score(responses, sample_size)
        
        return {
            'success': True,
            'mode': 'pmf',
            'question': question,
            'sample_size': sample_size,
            'actual_responses': len(responses),
            'viability_check': viability,
            'pmf_score': result['pmf_score'],
            'confidence_level': result['confidence'],
            'verdict': result['verdict'],
            'distribution': result['distribution'],
            'dissenters_feedback': result.get('dissenters', []),
            'next_suggestion': self._get_next_suggestion(result['verdict']),
        }
    
    def _check_commercial_viability(self, description: str) -> dict:
        """
        Pre-check commercial viability (3 questions):
          Q1: Who pays? (user / platform / supplier / split / unclear)
          Q2: Unit delivery cost? (<10 / 10-100 / 100-1000 / >1000 / unclear)
          Q3: Does supply side have motivation? (yes / conditional / no / unclear)
        """
        # In production: LLM evaluates these 3 questions
        return {
            'status': 'pre_checked',
            'q1_who_pays': 'pending_evaluation',
            'q2_unit_cost': 'pending_evaluation',
            'q3_supply_motivation': 'pending_evaluation',
        }
    
    def _generate_evaluation_personas(self, scenarios: list, target: int) -> list:
        """Generate diverse personas for PMF evaluation."""
        personas = []
        for i, scenario in enumerate(scenarios[:target]):
            persona = {
                'id': f'eval_{i+1:03d}',
                'scenario': scenario,
                'is_dissenter': False,
            }
            personas.append(persona)
        return personas
    
    def _generate_dissenters(self) -> list:
        """
        Generate 3 skeptical personas for robustness testing.
        
        Types:
          - Minimalist: Dislikes new features, wants simplicity
          - Trust-deficit: Skeptical of platform promises
          - Scene-mismatch: Usage scenario doesn't match the solution
        """
        dissenter_types = [
            {
                'id': 'dissenter_minimalist',
                'type': 'Minimalist',
                'persona': 'Dislikes additional features, believes less is more',
                'is_dissenter': True,
            },
            {
                'id': 'dissenter_trust_deficit', 
                'type': 'Trust-Deficit',
                'persona': 'Deeply skeptical of platform promises, assumes hidden catches',
                'is_dissenter': True,
            },
            {
                'id': 'dissenter_mismatch',
                'type': 'Scene-Mismatch', 
                'persona': 'Usage scenario completely misaligned with the solution',
                'is_dissenter': True,
            },
        ]
        return dissenter_types
    
    def _calculate_pmf_score(self, responses: List[PMFResponse], 
                              target_sample: int) -> dict:
        """
        Calculate PMF Score with confidence grading.
        
        Returns:
            dict with pmf_score, confidence, verdict, distribution
        """
        if not responses:
            # Return framework structure (populated by LLM in production)
            return {
                'pmf_score': None,
                'confidence': 'pending',
                'verdict': 'pending_evaluation',
                'distribution': {
                    'very_disappointed': 0,
                    'somewhat_disappointed': 0,
                    'not_very_disappointed': 0,
                    'dont_care': 0,
                },
                'confidence_interval': None,
            }
        
        # Count responses by level
        valid = [r for r in responses if not r.is_dissenter]
        n = len(valid)
        very_count = sum(1 for r in valid if r.disappointment_level == 'very')
        
        # PMF Score
        pmf_score = very_count / n if n > 0 else 0
        
        # 95% Confidence Interval (binomial approximation)
        ci = 1.96 * math.sqrt(pmf_score * (1 - pmf_score) / n) if n > 0 else 0
        
        # Confidence grading
        if n >= 20 and ci < 0.15:
            confidence = 'high'
        elif n >= 8:
            confidence = 'medium'
        else:
            confidence = 'low'
        
        # Verdict
        verdict = 'fail'
        for threshold, level, description in self.PMF_THRESHOLDS:
            if pmf_score >= threshold:
                verdict = level
                break
        
        return {
            'pmf_score': pmf_score,
            'confidence': confidence,
            'verdict': verdict,
            'distribution': {
                'very_disappointed': very_count,
                'somewhat_disappointed': sum(1 for r in valid if r.disappointment_level == 'somewhat'),
                'not_very_disappointed': sum(1 for r in valid if r.disappointment_level == 'not_very'),
                'dont_care': sum(1 for r in valid if r.disappointment_level == 'dont_care'),
            },
            'confidence_interval': (max(0, pmf_score - ci), min(1, pmf_score + ci)),
            'dissenters': [r for r in responses if r.is_dissenter],
        }
    
    def _get_next_suggestion(self, verdict: str) -> str:
        """Suggest next step based on PMF result."""
        suggestions = {
            'extreme': 'PMF is strong! Ready to proceed to PRD calibration?',
            'strong': 'PMF passed with high confidence. Move to PRD evaluation?',
            'pass': 'PMF achieved. Consider supplementing with 5-8 real interviews for confidence, then PRD.',
            'fail': 'PMF not achieved. Want to explore a different angle?',
            'pending_evaluation': 'Awaiting evaluation results.',
        }
        return suggestions.get(verdict, '')
