#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Virtual User Skill - Main Entry Point & Mode Router

Five working modes covering the full product lifecycle:
  1. explore   - 1v1 interview or debate (Idea stage)
  2. pmf       - PMF validation with Sean Ellis scale
  3. prd       - PRD calibration with 4-dimension scoring
  4. metrics   - Pre-launch metrics voting (Juster scale)
  5. debate    - Structured pro/con debate (alias for explore --debate)

Usage:
    python main.py --mode explore "What do users think about hotel upgrades?"
    python main.py --mode pmf "AI room upgrade feature" --sample 20
    python main.py --mode prd "Design A vs B vs C" --sample 20
    python main.py --mode metrics "Hotel upgrade" --metrics "click_rate,conversion" --sample 50
    python main.py --mode debate "Should we add AI recommendations?" --rounds 3
"""

import sys
import argparse
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent))


class VirtualUserSkill:
    """Virtual User Skill - AI User Research System
    
    Grounded in 140,000+ real user interview records and 54,000+ scenario entries.
    Five modes cover Idea → PMF → PRD → Pre-launch estimation.
    """
    
    MODES = {
        'explore': 'Exploration mode - 1v1 interview with virtual user',
        'debate': 'Debate mode - Pro vs Con structured debate',
        'pmf': 'PMF Validation - Sean Ellis disappointment scale',
        'prd': 'PRD Calibration - 4-dimension scoring + data validation plan',
        'metrics': 'Metrics Voting - Pre-launch business metric estimation',
    }
    
    def __init__(self, data_dir=None):
        self.data_dir = data_dir or (Path(__file__).parent.parent / "data")
        self._search_engine = None
        self._user_generator = None
    
    @property
    def search_engine(self):
        if self._search_engine is None:
            from vector_search import VectorSearchEngine
            self._search_engine = VectorSearchEngine(self.data_dir)
        return self._search_engine
    
    @property
    def user_generator(self):
        if self._user_generator is None:
            from user_generator import VirtualUserGenerator
            self._user_generator = VirtualUserGenerator()
        return self._user_generator
    
    def run(self, question: str, mode: str = 'explore', **kwargs):
        """
        Main entry point - routes to appropriate mode handler.
        
        Args:
            question: User's research question or scenario description
            mode: One of 'explore', 'debate', 'pmf', 'prd', 'metrics'
            **kwargs: Mode-specific parameters (sample, rounds, metrics, segment_by, etc.)
        
        Returns:
            dict: Mode-specific results
        """
        if mode not in self.MODES:
            raise ValueError(f"Unknown mode '{mode}'. Available: {list(self.MODES.keys())}")
        
        print(f"\n{'='*60}")
        print(f"  Virtual User Skill v2.0 - {self.MODES[mode]}")
        print(f"{'='*60}")
        print(f"\n  Question: {question}\n")
        
        # Route to mode handler
        handler = getattr(self, f'_run_{mode}')
        return handler(question, **kwargs)
    
    # ─────────────────────────────────────────────────────────────
    # Mode 1: Exploration (1v1 Interview)
    # ─────────────────────────────────────────────────────────────
    
    def _run_explore(self, question: str, **kwargs):
        """
        Exploration mode: Generate virtual user personas from scenario library,
        then conduct 1v1 deep interview.
        
        Flow:
          1. Vector search → retrieve relevant scenarios
          2. Generate 8-10 diverse persona types
          3. User selects personas
          4. Conduct interview (first-person role-play)
          5. Generate insights report
        """
        from modes.explore import ExploreMode
        
        mode_handler = ExploreMode(self.search_engine, self.user_generator)
        return mode_handler.run(question, **kwargs)
    
    # ─────────────────────────────────────────────────────────────
    # Mode 2: Debate (Pro vs Con)
    # ─────────────────────────────────────────────────────────────
    
    def _run_debate(self, question: str, rounds: int = 3, **kwargs):
        """
        Debate mode: Two opposing personas debate a topic.
        
        Args:
            question: Debate topic
            rounds: Number of debate rounds (1-5, default 3)
        
        Flow:
          1. Vector search → find relevant scenarios
          2. Generate Pro persona (supportive) and Con persona (skeptical)
          3. Structured debate for N rounds
          4. Synthesis and conclusion
        """
        from modes.explore import DebateMode
        
        mode_handler = DebateMode(self.search_engine, self.user_generator)
        return mode_handler.run(question, rounds=rounds, **kwargs)
    
    # ─────────────────────────────────────────────────────────────
    # Mode 3: PMF Validation
    # ─────────────────────────────────────────────────────────────
    
    def _run_pmf(self, question: str, sample: int = 20, **kwargs):
        """
        PMF Validation mode: Recruit N virtual users for independent evaluation.
        
        Core question: "If this feature didn't exist, how disappointed would you be?"
        
        Sean Ellis Scale:
          - Very disappointed (3) → Strong PMF signal
          - Somewhat disappointed (2) → Moderate signal
          - Not very disappointed (1) → Weak signal
          - Don't care (0) → No fit
        
        PMF Score = % "Very disappointed" / Total valid responses
        Pass threshold: >= 40%
        
        Args:
            question: Feature/solution description
            sample: Target sample size (default 20, min 8)
        
        Returns:
            dict with: pmf_score, confidence_level, verdict, beneficiary_groups,
                       improvement_directions, dissenter_feedback
        """
        from modes.pmf import PMFValidationMode
        
        mode_handler = PMFValidationMode(self.search_engine, self.user_generator)
        return mode_handler.run(question, sample_size=sample, **kwargs)
    
    # ─────────────────────────────────────────────────────────────
    # Mode 4: PRD Calibration
    # ─────────────────────────────────────────────────────────────
    
    def _run_prd(self, question: str, sample: int = 20, **kwargs):
        """
        PRD Calibration mode: N virtual users score solutions on 4 dimensions.
        
        Dimensions (weighted):
          - Need-Fit (30%): Does this solve a real pain point?
          - Experience Clarity (25%): Can users understand and use it quickly?
          - Potential Impact (25%): How much does it affect user behavior?
          - Priority Urgency (20%): How urgent/important do users feel this is?
        
        Each dimension scored 1-10, weighted composite calculated.
        
        Dual output:
          1. Scoring report: Feature ranking + experience blind spots + user quotes
          2. Data validation plan: Tracking events + metrics + analysis framework
        
        Args:
            question: Solution description (can be multiple alternatives)
            sample: Target sample size (default 20, min 8)
        """
        from modes.prd import PRDCalibrationMode
        
        mode_handler = PRDCalibrationMode(self.search_engine, self.user_generator)
        return mode_handler.run(question, sample_size=sample, **kwargs)
    
    # ─────────────────────────────────────────────────────────────
    # Mode 5: Metrics Voting
    # ─────────────────────────────────────────────────────────────
    
    def _run_metrics(self, question: str, sample: int = 50, 
                     metrics: str = "click_rate", segment_by: str = None, **kwargs):
        """
        Metrics Voting mode: Translate user attitudes into business metric estimates.
        
        5-point Juster Behavioral Intention Scale:
          - Definitely will (1.0)
          - Probably will (0.6)
          - Not sure (0.3)
          - Probably won't (0.1)
          - Definitely won't (0.0)
        
        Outputs per metric:
          1. Estimated percentage (weighted by scale + user segment weights)
          2. 95% confidence interval (binomial approximation)
          3. User segment breakdown (e.g., VIP vs regular)
          4. Top 3 rejection reasons (from "probably won't" + "definitely won't")
        
        Args:
            question: Solution/feature description
            sample: Target sample size (default 50, min 30)
            metrics: Comma-separated metric types (click_rate, conversion, retention, etc.)
            segment_by: Optional segmentation dimension
        """
        from modes.metrics import MetricsVotingMode
        
        metrics_list = [m.strip() for m in metrics.split(',')]
        mode_handler = MetricsVotingMode(self.search_engine, self.user_generator)
        return mode_handler.run(
            question, 
            sample_size=sample, 
            metrics=metrics_list,
            segment_by=segment_by, 
            **kwargs
        )


def main():
    """CLI entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description='Virtual User Skill - AI User Research System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --mode explore "What do users think about hotel upgrades?"
  %(prog)s --mode pmf "AI room upgrade" --sample 20
  %(prog)s --mode prd "Design A vs B" --sample 20
  %(prog)s --mode metrics "Upgrade feature" --metrics "click_rate,conversion" --sample 50
  %(prog)s --mode debate "Add AI recommendations?" --rounds 3
        """
    )
    
    parser.add_argument('question', help='Research question or scenario description')
    parser.add_argument('--mode', choices=VirtualUserSkill.MODES.keys(), 
                        default='explore', help='Working mode (default: explore)')
    parser.add_argument('--sample', type=int, default=None,
                        help='Sample size (default varies by mode)')
    parser.add_argument('--rounds', type=int, default=3,
                        help='Debate rounds (mode=debate only, default: 3)')
    parser.add_argument('--metrics', type=str, default='click_rate',
                        help='Comma-separated metrics (mode=metrics only)')
    parser.add_argument('--segment-by', type=str, default=None,
                        help='Segmentation dimension (mode=metrics only)')
    parser.add_argument('--auto', action='store_true',
                        help='Auto-select top personas without prompting')
    
    args = parser.parse_args()
    
    # Set mode-appropriate defaults
    sample_defaults = {
        'explore': 1, 'debate': 2, 'pmf': 20, 'prd': 20, 'metrics': 50
    }
    sample = args.sample or sample_defaults.get(args.mode, 20)
    
    # Run skill
    skill = VirtualUserSkill()
    
    try:
        result = skill.run(
            question=args.question,
            mode=args.mode,
            sample=sample,
            rounds=args.rounds,
            metrics=args.metrics,
            segment_by=args.segment_by,
            auto_select=args.auto,
        )
        
        if result.get('success'):
            print(f"\n{'='*60}")
            print(f"  Done. Mode: {args.mode} | Samples: {sample}")
            print(f"{'='*60}\n")
        else:
            print(f"\n  Execution failed: {result.get('error', 'Unknown error')}")
            sys.exit(1)
            
    except ImportError as e:
        print(f"\n  Mode '{args.mode}' requires additional modules: {e}")
        print(f"  Install with: pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"\n  Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
