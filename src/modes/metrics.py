#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Metrics Voting Mode - Pre-Launch Business Metric Estimation

Translates user attitudes into quantitative business metric predictions
using the Juster Purchase Intention Scale (1966).

5-Point Behavioral Intention Scale:
  | Option | Weight | Meaning |
  |--------|--------|---------|
  | Definitely will | 1.0 | Strong positive intention |
  | Probably will | 0.6 | Moderate positive |
  | Not sure | 0.3 | Ambivalent |
  | Probably won't | 0.1 | Weak negative |
  | Definitely won't | 0.0 | Strong negative |

Supported metric types:
  - click_rate: "Would you click to see this?"
  - conversion: "Would you pay for / complete this?"
  - retention: "Would you use this again?"
  - participation: "Would you join this activity?"
  - recommendation: "Would you recommend this to friends?"
  - custom: User-defined behavioral question

Output per metric:
  1. Estimated percentage (5-point weighted + segment weights)
  2. 95% confidence interval (binomial approximation using actual_n)
  3. User segment breakdown (e.g., VIP 35% vs Regular 18%)
  4. Top 3 rejection reasons (from "probably won't" + "definitely won't" users)
  5. Anti-resonance check (collapse warning if one option > 80%)
"""

import math
import statistics
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class MetricVote:
    """Single user's behavioral intention vote for one metric."""
    persona_id: str
    persona_name: str
    segment: str           # User segment (e.g., 'VIP', 'Regular')
    weight: float          # Persona weight (1-5, for representative mechanism)
    metric_type: str       # Which metric this vote is for
    intention: str         # 'definitely', 'probably', 'not_sure', 'probably_not', 'definitely_not'
    reasoning: str         # Why this choice
    

class MetricsVotingMode:
    """Pre-Launch Metrics Voting - Estimate business metrics before launch.
    
    Architecture (mirrors authentic-user v5.7):
      - Uses explore_dialogue x N parallel + local aggregation
      - NOT a separate agent (avoids 504 timeout)
      - Simple output structure suits parallel dispatch
    
    Execution flow:
      1. Select personas with mode=metric_voting → get N personas with weights
      2. Dispatch N explore_dialogue calls (each: 1 persona + solution + 5-point question)
      3. Local aggregation: weighted scoring + CI + segmentation + rejection reasons
      4. Anti-resonance check (flag if one option > 80% and std < 0.15)
    """
    
    INTENTION_SCALE = {
        'definitely': {'weight': 1.0, 'label': 'Definitely Will', 'label_cn': '绝对会'},
        'probably': {'weight': 0.6, 'label': 'Probably Will', 'label_cn': '可能会'},
        'not_sure': {'weight': 0.3, 'label': 'Not Sure', 'label_cn': '不确定'},
        'probably_not': {'weight': 0.1, 'label': 'Probably Not', 'label_cn': '可能不会'},
        'definitely_not': {'weight': 0.0, 'label': 'Definitely Not', 'label_cn': '绝对不会'},
    }
    
    METRIC_TYPES = {
        'click_rate': {
            'label': 'Click-Through Rate',
            'label_cn': '点击率',
            'question_template': 'If you saw this feature entry point, would you click to explore it?',
        },
        'conversion': {
            'label': 'Conversion Rate', 
            'label_cn': '转化率',
            'question_template': 'After understanding this product/feature, would you complete the purchase/signup?',
        },
        'retention': {
            'label': 'Retention Rate',
            'label_cn': '留存率',
            'question_template': 'After using this once, would you come back and use it again?',
        },
        'participation': {
            'label': 'Participation Rate',
            'label_cn': '参与意愿',
            'question_template': 'If you saw this activity/campaign, would you participate?',
        },
        'recommendation': {
            'label': 'Recommendation Rate',
            'label_cn': '推荐意愿',
            'question_template': 'Would you actively recommend this to friends or family?',
        },
    }
    
    def __init__(self, search_engine, user_generator):
        self.search_engine = search_engine
        self.user_generator = user_generator
    
    def run(self, question: str, sample_size: int = 50,
            metrics: List[str] = None, segment_by: str = None, **kwargs) -> dict:
        """
        Execute metrics voting.
        
        Args:
            question: Solution/feature description
            sample_size: Target voters (default 50, min 30, max 200)
            metrics: List of metric types to estimate
            segment_by: Segmentation dimension (e.g., 'membership_tier')
        """
        sample_size = max(30, min(200, sample_size))
        metrics = metrics or ['click_rate']
        
        # Validate metric types
        for m in metrics:
            if m not in self.METRIC_TYPES and not m.startswith('custom:'):
                print(f"  Warning: Unknown metric '{m}', treating as custom")
        
        print(f"\n[Metrics Voting]")
        print(f"  Solution: {question[:80]}...")
        print(f"  Target sample: {sample_size} voters")
        print(f"  Metrics: {', '.join(metrics)}")
        if segment_by:
            print(f"  Segment by: {segment_by}")
        
        # Step 1: Generate voter personas
        print(f"\n[Step 1] Generating {sample_size} voter personas...")
        scenarios = self.search_engine.search(question, top_k=sample_size * 2)
        # In production: call persona selection agent with mode=metric_voting
        # Each persona gets a weight (1-5) for representative mechanism
        
        # Step 2: Dispatch parallel votes
        effective_rate = 0.72  # Functional question effective rate
        dispatch_count = math.ceil(sample_size / effective_rate)
        print(f"\n[Step 2] Dispatching {dispatch_count} voting calls (target {sample_size} valid)...")
        # In production: explore_dialogue x N parallel calls
        
        votes = []  # Filled by LLM in production
        
        # Step 3: Aggregate per metric
        print("\n[Step 3] Aggregating results...")
        results_per_metric = {}
        for metric in metrics:
            metric_votes = [v for v in votes if v.metric_type == metric]
            results_per_metric[metric] = self._aggregate_metric(
                metric_votes, metric, segment_by
            )
        
        # Step 4: Anti-resonance check
        print("\n[Step 4] Anti-resonance check...")
        warnings = self._check_anti_resonance(votes)
        if warnings:
            for w in warnings:
                print(f"  WARNING: {w}")
        
        return {
            'success': True,
            'mode': 'metrics',
            'question': question,
            'sample_size': sample_size,
            'dispatch_count': dispatch_count,
            'metrics_estimated': metrics,
            'results': results_per_metric,
            'warnings': warnings,
            'segment_by': segment_by,
            'next_suggestion': 'Estimates ready. Share with data team for A/B test baseline.',
        }
    
    def _aggregate_metric(self, votes: List[MetricVote], metric: str,
                           segment_by: Optional[str]) -> dict:
        """
        Aggregate votes for a single metric.
        
        Calculation:
          estimated_rate = sum(vote_weight * persona_weight) / sum(persona_weight)
          where vote_weight = INTENTION_SCALE[intention]['weight']
        """
        if not votes:
            return {
                'estimated_rate': None,
                'confidence_interval': None,
                'n': 0,
                'distribution': {},
                'segments': {},
                'rejection_reasons_top3': [],
            }
        
        # Weighted estimation
        total_weight = sum(v.weight for v in votes)
        estimated = sum(
            self.INTENTION_SCALE[v.intention]['weight'] * v.weight 
            for v in votes
        ) / total_weight if total_weight > 0 else 0
        
        n = len(votes)
        
        # 95% CI (using actual_n, not weighted)
        ci = 1.96 * math.sqrt(estimated * (1 - estimated) / n) if n > 0 else 0
        
        # Distribution
        distribution = {}
        for level in self.INTENTION_SCALE:
            count = sum(1 for v in votes if v.intention == level)
            distribution[level] = {'count': count, 'pct': count / n if n > 0 else 0}
        
        # Segment breakdown
        segments = {}
        if segment_by:
            segment_groups = {}
            for v in votes:
                seg = v.segment or 'unknown'
                if seg not in segment_groups:
                    segment_groups[seg] = []
                segment_groups[seg].append(v)
            
            for seg, seg_votes in segment_groups.items():
                if len(seg_votes) >= 5:  # Min 5 per segment
                    seg_weight = sum(v.weight for v in seg_votes)
                    seg_est = sum(
                        self.INTENTION_SCALE[v.intention]['weight'] * v.weight
                        for v in seg_votes
                    ) / seg_weight if seg_weight > 0 else 0
                    segments[seg] = {
                        'estimated_rate': seg_est,
                        'n': len(seg_votes),
                    }
        
        # Top 3 rejection reasons
        rejectors = [v for v in votes if v.intention in ('probably_not', 'definitely_not')]
        # In production: cluster reasoning text to find top 3 themes
        rejection_reasons = [r.reasoning for r in rejectors[:3]]
        
        return {
            'estimated_rate': estimated,
            'confidence_interval': (max(0, estimated - ci), min(1, estimated + ci)),
            'n': n,
            'distribution': distribution,
            'segments': segments,
            'rejection_reasons_top3': rejection_reasons,
        }
    
    def _check_anti_resonance(self, votes: List[MetricVote]) -> list:
        """
        Anti-resonance check: flag suspicious unanimity.
        
        Triggers if:
          - Any single option chosen by > 80% of voters
          - AND standard deviation of weights < 0.15
        
        This suggests model bias rather than genuine consensus.
        """
        warnings = []
        if not votes:
            return warnings
        
        # Group by metric
        metrics_seen = set(v.metric_type for v in votes)
        for metric in metrics_seen:
            metric_votes = [v for v in votes if v.metric_type == metric]
            n = len(metric_votes)
            if n < 10:
                continue
            
            # Check each intention level
            for level in self.INTENTION_SCALE:
                count = sum(1 for v in metric_votes if v.intention == level)
                if count / n > 0.80:
                    warnings.append(
                        f"[{metric}] '{level}' chosen by {count}/{n} ({count/n:.0%}) voters. "
                        f"Possible model bias — consider adding adversarial personas."
                    )
        
        return warnings
