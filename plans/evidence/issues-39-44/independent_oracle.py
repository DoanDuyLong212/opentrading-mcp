from fractions import Fraction as F
from copy import deepcopy
from opentrading_mcp.forensic_models import calculate_forensic

vals=[{'assets':100}, {'assets':120,'revenue':150,'receivables':15,'gross':60,'net_income':24,'cfo':20,'current_assets':60,'current_liabilities':30,'net_ppe':30,'long_term_debt':30,'current_portion_long_term_debt':6,'depreciation':6,'selling':10,'admin':5}, {'assets':200,'revenue':180,'receivables':18,'gross':54,'net_income':20,'cfo':15,'current_assets':70,'current_liabilities':40,'net_ppe':60,'long_term_debt':40,'current_portion_long_term_debt':8,'depreciation':6,'selling':12,'admin':9,'equity_issued':True}]
b={'symbol':'ORACLE','latest_observed_year':2025,'records':[dict(year=y,period_start=f'{y}-01-01',period_end=f'{y}-12-31',company_id=1,scope='consolidated',source='independent',business_type='general',statements=['CDKT','KQKD','LCTT'],values=v) for y,v in zip([2023,2024,2025],vals)]}
d=calculate_forensic(b)
indexes=dict(dsri=F(1),gmi=F(4,3),aqi=F(7,5),sgi=F(6,5),depi=F(11,6),sgai=F(7,6),tata=F(1,40),lvgi=F(4,5))
# Independent fixed coefficients, never import model coefficients.
m=-F(484,100)+F(920,1000)*indexes['dsri']+F(528,1000)*indexes['gmi']+F(404,1000)*indexes['aqi']+F(892,1000)*indexes['sgi']+F(115,1000)*indexes['depi']-F(172,1000)*indexes['sgai']+F(4679,1000)*indexes['tata']-F(327,1000)*indexes['lvgi']
for k,v in indexes.items(): assert d[k]==round(float(v),4),(k,d[k],v)
assert d['m_score']==round(float(m),4),(d['m_score'],m)
want=dict(positive_roa=True,positive_cfo=True,roa_increased=False,cfo_above_roa=False,leverage_decreased=True,current_ratio_increased=False,no_equity_issuance=False,gross_margin_increased=False,turnover_increased=False)
assert {k:v['passed'] for k,v in d['f_components'].items()}==want,d['f_components']
assert d['f_score']=='3/9'
print('PASS independent Fraction oracle: 8 indices, M-score',float(m),'9 mixed signals, F-score 3/9')
for financial in ['bank','securities','insurance']:
 c=deepcopy(b)
 for r in c['records']: r['business_type']=financial
 x=calculate_forensic(c); assert x['m_score'] is None and x['f_score'] is None and x['beneish']['status']=='not_applicable' and x['piotroski']['status']=='unsupported'
print('PASS financial scope gating: bank/securities/insurance')
c=deepcopy(b);c['latest_observed_year']=2026
x=calculate_forensic(c);assert x['m_score'] is None and x['f_score'] is None and x['data_time'] is None
print('PASS invalid newest does not silently score old annual data')
c=deepcopy(b);c['records'].pop(0)
x=calculate_forensic(c);assert x['m_score']==d['m_score'] and x['f_score'] is None and x['f_evaluated']==6
print('PASS two vs three annual balances')
for field in ['assets','revenue','gross','net_ppe','current_assets','long_term_debt','current_liabilities','receivables','depreciation','selling','admin','cfo','net_income']:
 c=deepcopy(b);del c['records'][-1]['values'][field]
 x=calculate_forensic(c);assert x['m_score'] is None,(field,x['m_score'])
print('PASS missing each of 13 current Beneish input fields blocks complete score')
c=deepcopy(b);c['records'][-1]['values'].update(receivables=0,selling=0,admin=0,cfo=0,net_income=0)
x=calculate_forensic(c);assert x['dsri']==x['sgai']==x['tata']==0 and x['m_score'] is not None
assert x['f_components']['positive_roa']['passed'] is False and x['f_components']['positive_cfo']['passed'] is False
print('PASS zero data preserved and correctly scores failed positive signals')
