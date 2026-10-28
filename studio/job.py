"""Fetch a render job from sygil-sites and embed the logo as a data URL (so the page never needs the network for it)."""
import base64, json, sys, urllib.request
slug, out = sys.argv[1], sys.argv[2]
UA = {'user-agent': 'sygil-studio/1.0'}
def get(u): return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30).read()
job = json.loads(get(f'https://sygil.pro/api/video-job?slug={slug}'))
if job.get('error'): sys.exit(f'{slug}: {job["error"]}')
if job.get('logoUrl'):
    try:
        req = urllib.request.urlopen(urllib.request.Request(job['logoUrl'], headers=UA), timeout=30)
        ct = req.headers.get('content-type', 'image/png').split(';')[0]; data = req.read()
        if ct.startswith('image/') and len(data) < 5e6: job['logo'] = f'data:{ct};base64,' + base64.b64encode(data).decode()
    except Exception as e: print('logo failed', e)
json.dump(job, open(out, 'w')); print('job ok', slug, job.get('family'))
