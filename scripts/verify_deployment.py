"""Verify a user-authorized public HTTPS deployment. Default: ZERO model calls.

--live makes at most two fictional /api/chat requests, tracked BEFORE sending in
an ignored local budget file. Never reset the budget to repeat this phase's tests.
No credentials are transmitted by this script; the server holds Gemini settings.
"""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import sys
from urllib.parse import urlparse

import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from nyaysaathi.knowledge import load_knowledge
from nyaysaathi.settings import get_settings
from scripts.audit_publication import PATTERNS

BUDGET=ROOT/'.pytest_cache/phase10_live_budget.json'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--live',action='store_true')
    args=parser.parse_args()
    url=args.url.rstrip('/')
    parsed=urlparse(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
        parser.error('Provide the authorized HTTPS origin only, without credentials, path or query.')
    key=get_settings().gemini_api_key
    results={'url':url,'endpoint_checks':[],'live_tests':[]}
    with httpx.Client(timeout=55,follow_redirects=False) as client:
        for path in ('/','/api/health','/static/styles.css','/static/app.js','/static/audio.js','/static/pcm-worklet.js'):
            response=client.get(url+path)
            leaked=bool(key and key in response.text) or any(pattern.search(response.text) for pattern in PATTERNS.values())
            result={'path':path,'status':response.status_code,'secret_scan_passed':not leaked}
            results['endpoint_checks'].append(result)
            if response.status_code!=200 or leaked:
                print(json.dumps(results,indent=2));return 1
        invalid=client.post(url+'/api/chat',json={'message':'','verified':True})
        results['invalid_request_status']=invalid.status_code
        if invalid.status_code!=422:
            print(json.dumps(results,indent=2));return 1
        if args.live:
            budget=json.loads(BUDGET.read_text()) if BUDGET.exists() else {'attempted':0}
            if budget['attempted']!=0:
                raise SystemExit('Phase 10 live budget already started/spent. No repeated requests will be made.')
            fixtures=[
                ('English defects','I ordered headphones worth ₹2,999 online. They arrived damaged, and the seller is refusing a refund.','en',Decimal('2999')),
                ('Hinglish non-delivery','Maine Flipkart se ₹4500 ka product order kiya tha, lekin delivery nahi hui. Mujhe refund chahiye.','hinglish',Decimal('4500')),
            ]
            official={entry.source_id:entry for entry in load_knowledge()}
            BUDGET.parent.mkdir(exist_ok=True)
            for name,message,language,amount in fixtures:
                budget['attempted']+=1;budget['url']=url
                BUDGET.write_text(json.dumps(budget),encoding='utf-8')
                response=client.post(url+'/api/chat',json={'message':message,'language':language,'case':{},'history':[]})
                result={'test':name,'status':response.status_code}
                if response.status_code==200:
                    payload=response.json();case=payload['case'];citations=payload['guidance']['citations']
                    seller=case['company_or_seller']
                    issue=(case['issue_type'] or '').casefold()
                    result.update(amount_correct=Decimal(case['amount_inr'])==amount if case['amount_inr'] is not None else False,
                        date_unknown=case['incident_date'] is None,evidence_not_invented=case['evidence_available']==[],
                        seller_correct=seller is None if language=='en' else any(term in (seller or '').casefold() for term in ('flipkart','फ्लिपकार्ट')),
                        issue_classified=any(term in issue for term in (('defect','damage','खराब','क्षतिग्रस्त') if language=='en' else ('deliver','non','डिलीवरी','नहीं'))),
                        reply_present=bool(payload['reply']),intake_valid=payload['error'] is None,
                        guidance_grounded=payload['guidance']['status']=='grounded',
                        citations_valid=bool(citations) and all(item['source_id'] in official and item['url']==official[item['source_id']].source_url and item['explanation']==official[item['source_id']].guidance[payload['guidance']['language']] for item in citations))
                results['live_tests'].append(result)
            results['live_request_attempts']=budget['attempted']
    print(json.dumps(results,indent=2))
    return 0 if all(all(value is True for key,value in item.items() if key not in ('test','status')) and item['status']==200 for item in results['live_tests']) else 1


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except httpx.HTTPError:
        raise SystemExit('HTTPS verification failed. No retry was made; check the existing live budget before any further requests.') from None
