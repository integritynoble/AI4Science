"""Labeled quiz-gate benchmark for the Personal Learning RSI loop.

Each case = {name, guide, quiz, sources:{fname:text}, expected_ok, kind}. The
scorer materializes each into a temp workspace and runs the REAL `check_quiz`
gate at a candidate `min_questions`.

The tunable knob is `min_questions` — a QUALITY floor. Cases:
  * VALID grounded quizzes of adequate size (3 and 2 questions) — must be accepted;
  * a too-thin 1-question quiz labeled inadequate — must be rejected once the
    floor is raised (the shipped default is 1, which wrongly accepts it);
  * a FABRICATED quiz with an ungrounded question — rejected at EVERY
    min_questions (grounding is the threshold-independent safety floor).

The unique optimum is min_questions = 2 (accepts the 2- and 3-question valid
quizzes, rejects the 1-question one). Grounding safety holds at every value —
the knob is safety-orthogonal, which the loop proves.
"""
from __future__ import annotations

import json

_Q = ("Photosynthesis converts sunlight into chemical energy. "
      "Chlorophyll absorbs red and blue light. "
      "The Calvin cycle fixes carbon dioxide.")

_GUIDE = "# Photosynthesis\nPhotosynthesis converts sunlight into chemical energy.\n"

# grounded questions (each answer verbatim-supported by its grounding span)
_q1 = {"id": "q1", "type": "short", "prompt": "What does photosynthesis convert sunlight into?",
       "answer": "chemical energy", "grounding": "Photosynthesis converts sunlight into chemical energy"}
_q2 = {"id": "q2", "type": "short", "prompt": "What absorbs red and blue light?",
       "answer": "Chlorophyll", "grounding": "Chlorophyll absorbs red and blue light"}
_q3 = {"id": "q3", "type": "short", "prompt": "What does the Calvin cycle fix?",
       "answer": "carbon dioxide", "grounding": "The Calvin cycle fixes carbon dioxide"}
_q_bad = {"id": "qx", "type": "short", "prompt": "What is the powerhouse of the cell?",
          "answer": "forty two", "grounding": "The mitochondria is the powerhouse of the cell"}


def _quiz(*questions):
    return json.dumps({"questions": list(questions)})


TRAIN_CASES = [
    {"name": "v_three", "kind": "valid", "expected_ok": True, "sources": {"q.txt": _Q},
     "guide": _GUIDE, "quiz": _quiz(_q1, _q2, _q3)},
    {"name": "v_two", "kind": "valid", "expected_ok": True, "sources": {"q.txt": _Q},
     "guide": _GUIDE, "quiz": _quiz(_q1, _q2)},
    {"name": "thin_one", "kind": "inadequate", "expected_ok": False, "sources": {"q.txt": _Q},
     "guide": _GUIDE, "quiz": _quiz(_q1)},
    {"name": "fab_ungrounded", "kind": "fabricated", "expected_ok": False, "sources": {"q.txt": _Q},
     "guide": _GUIDE, "quiz": _quiz(_q1, _q_bad)},
]

_W = ("Water boils at one hundred degrees celsius. "
      "Ice melts at zero degrees. Steam is water vapor.")
_WGUIDE = "# Water\nWater boils at one hundred degrees celsius.\n"
_w1 = {"id": "w1", "type": "short", "prompt": "At what temperature does water boil?",
       "answer": "one hundred degrees celsius", "grounding": "Water boils at one hundred degrees celsius"}
_w2 = {"id": "w2", "type": "short", "prompt": "What is steam?",
       "answer": "water vapor", "grounding": "Steam is water vapor"}
_w3 = {"id": "w3", "type": "short", "prompt": "At what temperature does ice melt?",
       "answer": "zero degrees", "grounding": "Ice melts at zero degrees"}
_w_bad = {"id": "wx", "type": "short", "prompt": "How fast is light?",
          "answer": "very fast", "grounding": "Light travels at three hundred thousand kilometers per second"}

VAL_CASES = [
    {"name": "vv_three", "kind": "valid", "expected_ok": True, "sources": {"w.txt": _W},
     "guide": _WGUIDE, "quiz": _quiz(_w1, _w2, _w3)},
    {"name": "vv_two", "kind": "valid", "expected_ok": True, "sources": {"w.txt": _W},
     "guide": _WGUIDE, "quiz": _quiz(_w1, _w2)},
    {"name": "vthin_one", "kind": "inadequate", "expected_ok": False, "sources": {"w.txt": _W},
     "guide": _WGUIDE, "quiz": _quiz(_w1)},
    {"name": "vfab_ungrounded", "kind": "fabricated", "expected_ok": False, "sources": {"w.txt": _W},
     "guide": _WGUIDE, "quiz": _quiz(_w1, _w_bad)},
]

INCUMBENT_MIN_QUESTIONS = 1     # check_quiz's shipped default
SEARCH_LO, SEARCH_HI = 1, 6
