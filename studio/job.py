"""Fetch a render job from sygil-sites and embed the logo as a data URL (so the page never needs the network for it)."""
import base64, json, sys, urllib.request
tok, out = sys.argv[1], sys.argv[2]
slug, _, cut = tok.partition(':')  # 'slug' = launch video, 'slug:teaser' / 'slug:milestone' = Legend video pack
UA = {'user-agent': 'sygil-studio/1.0'}
def get(u): return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30).read()
job = json.loads(get(f'https://sygil.pro/api/video-job?slug={slug}' + (f'&cut={cut}' if cut else '')))
if job.get('error'): sys.exit(f'{slug}: {job["error"]}')
if not job.get('logoUrl'):  # no logo, no video
    sys.exit(f'{slug}: no logo url, skipped')
if job.get('logoUrl'):
    import time
    for attempt in range(4):  # the logo host is sometimes slow: retry before giving up
        try:
            req = urllib.request.urlopen(urllib.request.Request(job['logoUrl'], headers=UA), timeout=45)
            ct = req.headers.get('content-type', 'image/png').split(';')[0]; data = req.read()
            ok = data[:8] == b'\x89PNG\r\n\x1a\n' or data[:3] == b'\xff\xd8\xff' or data[:4] == b'GIF8' or (data[:4] == b'RIFF' and data[8:12] == b'WEBP') or b'ftypavif' in data[:32] or data.lstrip()[:5] in (b'<svg ', b'<?xml')
            if ct.startswith('image/') and ok and 0 < len(data) < 5e6: job['logo'] = f'data:{ct};base64,' + base64.b64encode(data).decode(); break
        except Exception as e: print('logo attempt', attempt + 1, 'failed', e)
        time.sleep(10 * (attempt + 1))
    if not job.get('logo'):  # never publish a video without the coin's logo: skip now, a later run retries
        sys.exit(f'{slug}: logo not reachable, skipped (will retry next run)')
json.dump(job, open(out, 'w')); print('job ok', tok, job.get('family'))
