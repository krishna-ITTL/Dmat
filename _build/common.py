import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
J = lambda *p: os.path.join(ROOT, *p)
SRC = {
    'official': J('Academic Module', '260902_dMAT_General-Academic-Module_Preparatoy-Materials_EN (1).pdf'),
    'gaprac': J('Academic Module', 'Subject-Module-Practice-Set-Expanded (1).pdf'),
    'doubt': J('CORE MODULE', 'Figure Series', 'dMAT_Doubt_Session_v4.pdf'),
    'fs50': J('CORE MODULE', 'Figure Series', 'Figure_Sequences_50_Practice_Questions.pdf'),
    'fsadv': J('CORE MODULE', 'Figure Series', 'Figure_Sequences_50_Advanced_Practice_Questions.pdf'),
    'fsexp': J('CORE MODULE', 'Figure Series', 'Figure_Sequences_50_Expert_Practice_Questions.pdf'),
    'c2': J('CORE MODULE', 'Mathematical Equation', 'c2_Two_Three_Unknowns.pdf'),
    'c3': J('CORE MODULE', 'Mathematical Equation', 'c3_Three_Four_Unknowns.pdf'),
    'c4': J('CORE MODULE', 'Mathematical Equation', 'c4_Four_Five_Unknowns_Full_Exam_Readiness.pdf'),
    'masters': J('CORE MODULE', 'Latin Square', 'dMAT_Germany_Masters_Test_100_Q_Reordered.pdf'),
    'core150': J('CORE MODULE', 'Mathematical Equation', 'dMAT_Core_Module_150_Practice_Questions.pdf'),
    'ls1': J('CORE MODULE', 'Latin Square', '1Done.pdf'),
    'ls2': J('CORE MODULE', 'Mathematical Equation', 'Class_2_Chain_Deduction_2hr.pdf'),
    'ls3': J('CORE MODULE', 'Figure Series', 'Class_3_MultiStep_WholeGrid_2hr.pdf'),
}
DOCNAME = {k: os.path.basename(v) for k, v in SRC.items()}


def norm(s):
    return s.replace('–', '-').replace('−', '-').replace(' ', ' ').replace(' ', ' ')
