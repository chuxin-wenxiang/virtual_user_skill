#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Exploration Mode - 1v1 Interview & Debate

Two sub-modes:
  1. ExploreMode: Single virtual user deep interview
  2. DebateMode: Pro vs Con structured debate (1-5 rounds)
"""

from typing import List, Dict, Optional


class ExploreMode:
    """1v1 Deep Interview with a Virtual User Persona
    
    Flow:
      1. Retrieve relevant scenarios via vector search
      2. Generate 8-10 diverse persona types
      3. User selects persona(s)
      4. Conduct interview in first-person role-play
      5. Generate insights report
    """
    
    def __init__(self, search_engine, user_generator):
        self.search_engine = search_engine
        self.user_generator = user_generator
    
    def run(self, question: str, auto_select: bool = False, **kwargs) -> dict:
        """Execute exploration interview."""
        
        # Step 1: Vector search for relevant scenarios
        print("\n[Step 1] Searching scenario library...")
        scenarios = self.search_engine.search(question, top_k=20)
        print(f"  Found {len(scenarios)} relevant scenarios")
        
        # Step 2: Generate diverse persona types
        print("\n[Step 2] Generating virtual user personas...")
        user_types = self.user_generator.generate_user_types(scenarios, top_n=10)
        print(self.user_generator.format_user_list())
        
        # Step 3: User selection
        if auto_select:
            self.user_generator.select_all(selected=False)
            for i in range(min(3, len(user_types))):
                self.user_generator.toggle_selection(i + 1, selected=True)
            print("  [Auto-selected top 3 personas]")
        
        selected_users = self.user_generator.get_selected_users()
        
        # Step 4: Conduct interview
        print(f"\n[Step 4] Starting interview with {len(selected_users)} persona(s)...")
        conversations = []
        for user in selected_users:
            # In full implementation, this would invoke LLM with persona context
            conversation = {
                'persona': user['type_name'],
                'profile': user['profile'],
                'responses': [],  # Filled by LLM in production
            }
            conversations.append(conversation)
        
        # Step 5: Generate report
        print("\n[Step 5] Generating insights report...")
        
        return {
            'success': True,
            'mode': 'explore',
            'question': question,
            'personas_generated': len(user_types),
            'personas_selected': len(selected_users),
            'conversations': conversations,
            'next_suggestion': 'Want to validate PMF with 20 people?'
        }


class DebateMode:
    """Structured Pro vs Con Debate between Two Personas
    
    Flow:
      1. Retrieve scenarios → generate Pro persona + Con persona
      2. Conduct N rounds of structured debate
      3. Generate synthesis and conclusion
    
    Rules:
      - Pro: Supports the idea/feature (typically a power user or target segment)
      - Con: Skeptical/opposing (typically a casual user or non-target)
      - Each round: Pro speaks → Con responds → (optional rebuttal)
      - Final: Moderator synthesizes key arguments and conclusion
    """
    
    def __init__(self, search_engine, user_generator):
        self.search_engine = search_engine
        self.user_generator = user_generator
    
    def run(self, question: str, rounds: int = 3, **kwargs) -> dict:
        """Execute debate."""
        
        rounds = max(1, min(5, rounds))  # Clamp to 1-5
        
        print(f"\n[Debate] Topic: {question}")
        print(f"[Debate] Rounds: {rounds}")
        
        # Step 1: Generate opposing personas
        print("\n[Step 1] Generating debate personas...")
        scenarios = self.search_engine.search(question, top_k=20)
        
        # Split scenarios into supportive vs skeptical based on sentiment
        pro_scenarios = [s for s in scenarios if s.get('情绪标签', '') in ['满意', '期待', '兴奋', '']]
        con_scenarios = [s for s in scenarios if s.get('情绪标签', '') in ['不满', '失望', '焦虑', '愤怒']]
        
        # Fallback: use first half as pro, second half as con
        if not pro_scenarios:
            pro_scenarios = scenarios[:len(scenarios)//2]
        if not con_scenarios:
            con_scenarios = scenarios[len(scenarios)//2:]
        
        print(f"  Pro persona based on {len(pro_scenarios)} supportive scenarios")
        print(f"  Con persona based on {len(con_scenarios)} skeptical scenarios")
        
        # Step 2: Conduct debate rounds
        debate_transcript = []
        for round_num in range(1, rounds + 1):
            print(f"\n[Round {round_num}/{rounds}]")
            # In production: LLM generates arguments for each side
            debate_transcript.append({
                'round': round_num,
                'pro_argument': None,  # Filled by LLM
                'con_argument': None,  # Filled by LLM
            })
        
        # Step 3: Synthesis
        print("\n[Synthesis] Generating conclusion...")
        
        return {
            'success': True,
            'mode': 'debate',
            'topic': question,
            'rounds': rounds,
            'transcript': debate_transcript,
            'conclusion': None,  # Filled by LLM synthesis
            'next_suggestion': 'Want to validate this direction with PMF?'
        }
