import runpy
from pathlib import Path
from copy import deepcopy
from opentrading_mcp.forensic_models import calculate_forensic
base=runpy.run_path(str(Path(__file__).with_name('independent_oracle.py')))['b']
for before,after,want in [(-30,-18,True),(-30,18,True),(-15,-36,False),(-30,-36,False),(0,0,False),(-30,0,True)]:
 b=deepcopy(base);b['records'][-2]['values']['gross']=before;b['records'][-1]['values']['gross']=after
 d=calculate_forensic(b)
 # revenue differs: prev 150, current 180. -30/150 == -36/180 exactly.
 assert d['f_components']['gross_margin_increased']['passed'] is want,(before,after,d['f_components']['gross_margin_increased'])
 assert d['f_evaluated']==9 and d['f_score'] is not None
 if before<0 or after<0:
  assert d['m_score'] is None
print('PASS independent signed gross margin oracle: six positive/negative/zero/equality transitions; Piotroski evaluates all nine while Beneish rejects negative gross domain')
