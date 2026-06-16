#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PRD Calibration Mode - 4-Dimension Solution Scoring

Evaluates specific solution designs across 4 weighted dimensions,
then automatically generates a data validation plan for post-launch monitoring.

Dimensions:
  1. Need-Fit (30%): Does this solve a real user pain point?
  2. Experience Clarity (25%): Can users quickly understand and use it?
  3. Potential Impact (25%): How much does it affect user behavior/decisions?
  4. Priority Urgency (20%): How urgent/important do users feel this is?

Each dimension scored 1-10. Weighted composite determines ranking.

Quality mechanisms:
  - Devil's Advocate (DA): Extra skeptical personas when consensus is too strong
  - Score dispersion check: SD < 1.0 + agreement > 80% triggers DA round
  - Prompt wording sensitivity: Multiple negative dimensions to avoid bias
"""

import statistics
from typing import List, Dict, Optional
from dataclasses import dataclass, field


@dataclass
class PRDScore:
    """Single persona's PRD evaluation scores."""
    persona_id: str
    persona_name: str
    solution_id: str
    need_fit: int          # 1-10
    experience_clarity: int  # 1-10
    potential_impact: int    # 1-10
    priority_urgency: int    # 1-10
    reasoning: str = ""
    is_devil_advocate: bool = False
    
    @property
    def weighted_score(self) -> float:
        """Calculate weighted composite score."""
        return (
            self.need_fit * 0.30 +
            self.experience_clarity * 0.25 +
            self.potential_impact * 0.25 +
            self.priority_urgency * 0.20
        )


class PRDCalibrationMode:
    """PRD Calibration - Score solutions and generate data validation plan.
    
    Dual Output:
      1. Scoring Report: Feature ranking + experience blind spots + user quotes
      2. Data Validation Plan: Tracking events + metrics + analysis framework
    
    The validation plan logic:
      "20 users told you what they care about → derive what data to track post-launch
       → from user needs, reverse-engineer the verification framework"
    """
    
    DIMENSIONS = {
        'need_fit': {'weight': 0.30, 'label': 'Need-Fit', 'label_cn': '需求匹配度',
                     'question': 'Does this solve a real pain point you have?'},
        'experience_clarity': {'weight': 0.25, 'label': 'Experience Clarity', 'label_cn': '体验清晰度',
                               'question': 'Can you quickly understand how to use this?'},
        'potential_impact': {'weight': 0.25, 'label': 'Potential Impact', 'label_cn': '潜在影响',
                             'question': 'How much would this change your behavior/decisions?'},
        'priority_urgency': {'weight': 0.20, 'label': 'Priority Urgency', 'label_cn': '优先紧迫度',
                             'question': 'How urgently do you want this?'},
    }
    
    def __init__(self, search_engine, user_generator):
        self.search_engine = search_engine
        self.user_generator = user_generator
    
    def run(self, question: str, sample_size: int = 20,
            user_group: str = None, **kwargs) -> dict:
        """
        Execute PRD calibration.
        
        Args:
            question: Solution description (can contain multiple alternatives separated by /)
            sample_size: Target evaluators (default 20, min 8)
            user_group: Target user segment
        """
        sample_size = max(8, sample_size)
        
        # Parse multiple solutions if present
        solutions = self._parse_solutions(question)
        
        print(f"\n[PRD Calibration]")
        print(f"  Solutions to evaluate: {len(solutions)}")
        print(f"  Target sample: {sample_size} users")
        for i, sol in enumerate(solutions, 1):
            print(f"    {chr(64+i)}. {sol[:60]}...")
        
        # Step 1: Generate evaluation personas
        print("\n[Step 1] Generating evaluation personas...")
        scenarios = self.search_engine.search(question, top_k=sample_size * 2)
        # In production: use explore_dialogue x N parallel architecture
        
        # Step 2: Parallel evaluation
        print(f"\n[Step 2] Collecting {sample_size} evaluations per solution...")
        # In production: parallel LLM calls with scoring prompt
        scores = []  # Filled by LLM evaluation
        
        # Step 3: Aggregate scores
        print("\n[Step 3] Aggregating scores...")
        aggregated = self._aggregate_scores(scores, solutions)
        
        # Step 4: Dispersion check & Devil's Advocate
        print("\n[Step 4] Checking score dispersion...")
        da_triggered = self._check_dispersion(scores)
        if da_triggered:
            print("  DA triggered: consensus too strong, adding skeptical personas")
        
        # Step 5: Generate data validation plan
        print("\n[Step 5] Generating data validation plan...")
        validation_plan = self._generate_validation_plan(question, solutions, aggregated)
        
        return {
            'success': True,
            'mode': 'prd',
            'question': question,
            'solutions': solutions,
            'sample_size': sample_size,
            'scores': aggregated,
            'ranking': self._rank_solutions(aggregated),
            'da_triggered': da_triggered,
            'validation_plan': validation_plan,
            'next_suggestion': 'Solutions scored. Want pre-launch metrics voting?',
        }
    
    def _parse_solutions(self, question: str) -> list:
        """Parse multiple solution alternatives from input."""
        # Look for common separators: vs, VS, 方案A/B/C, numbered lists
        if ' vs ' in question.lower():
            return [s.strip() for s in question.split(' vs ')]
        elif '方案' in question:
            import re
            parts = re.split(r'方案[A-Z][:：]?', question)
            return [p.strip() for p in parts if p.strip()]
        else:
            return [question]
    
    def _aggregate_scores(self, scores: List[PRDScore], solutions: list) -> dict:
        """Aggregate scores by solution and dimension."""
        result = {}
        for sol in solutions:
            sol_scores = [s for s in scores if s.solution_id == sol]
            if sol_scores:
                result[sol] = {
                    'weighted_mean': statistics.mean(s.weighted_score for s in sol_scores),
                    'dimensions': {
                        dim: {
                            'mean': statistics.mean(getattr(s, dim) for s in sol_scores),
                            'median': statistics.median(getattr(s, dim) for s in sol_scores),
                            'std': statistics.stdev(getattr(s, dim) for s in sol_scores) if len(sol_scores) > 1 else 0,
                        }
                        for dim in self.DIMENSIONS
                    },
                    'n': len(sol_scores),
                }
            else:
                result[sol] = {'weighted_mean': None, 'dimensions': {}, 'n': 0}
        return result
    
    def _rank_solutions(self, aggregated: dict) -> list:
        """Rank solutions by weighted composite score."""
        ranked = sorted(
            [(sol, data['weighted_mean']) for sol, data in aggregated.items() if data['weighted_mean']],
            key=lambda x: x[1],
            reverse=True
        )
        return [{'solution': sol, 'score': score, 'rank': i+1} for i, (sol, score) in enumerate(ranked)]
    
    def _check_dispersion(self, scores: List[PRDScore]) -> bool:
        """
        Check if results show suspiciously low dispersion.
        Triggers Devil's Advocate if:
          - Any dimension SD < 1.0 AND top agreement > 80%
          - Key reasoning phrases overlap > 70%
        """
        if len(scores) < 5:
            return False
        # Framework: would analyze actual scores in production
        return False
    
    def _generate_validation_plan(self, question: str, solutions: list, 
                                    aggregated: dict) -> dict:
        """
        Auto-generate post-launch data validation plan.
        
        Derived from what users said they care about:
          - Tracking events: Key behavioral events on core user path
          - Collection requirements: What metrics, how long, sample sizing
          - Monitoring metrics: Success criteria from user concerns
          - Analysis framework: What to compare, segment, trend-watch
        """
        return {
            'tracking_events': [
                # Filled based on solution type and user feedback themes
                'Feature entry point click',
                'Core action completion',
                'Return visit within 7 days',
            ],
            'collection_requirements': {
                'metrics': ['click_through_rate', 'conversion', 'time_on_task'],
                'duration': '2 weeks minimum',
                'sample': 'A/B test with >= 1000 users per arm',
            },
            'monitoring_metrics': {
                'primary': 'Core conversion rate',
                'secondary': ['Bounce rate', 'Task completion time', 'NPS delta'],
                'guardrail': ['Page load time', 'Error rate', 'Support tickets'],
            },
            'analysis_framework': {
                'comparison': 'Treatment vs Control',
                'segmentation': 'By user tier, frequency, device',
                'timeline': 'Day 1, Day 7, Day 30 cohort analysis',
            },
        }
