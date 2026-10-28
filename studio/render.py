"""Coin video renderer: job JSON -> 1080x1920 mp4 (frame-exact seek(t) in headless Chromium -> ffmpeg) + mood score + loudnorm + QA.
usage: python3 render.py job.json out.mp4 [--fps 30] [--stills]"""
import asyncio, json, os, subprocess, sys, pathlib, time
from playwright.async_api import async_playwright

HERE = pathlib.Path(__file__).resolve().parent
job_path, out = sys.argv[1], sys.argv[2]
FPS = int(sys.argv[sys.argv.index('--fps') + 1]) if '--fps' in sys.argv else 30
STILLS = '--stills' in sys.argv
job = json.load(open(job_path))
MOOD = {'war': 'military', 'cat': 'playful', 'dog': 'playful', 'frog': 'playful', 'spooky': 'spooky', 'luxe': 'luxury',
        'retro': 'synthwave', 'space': 'synthwave', 'anime': 'jpop'}.get(job.get('family'), 'trap')

async def frames():
    async with async_playwright() as p:
        b = await p.chromium.launch(args=['--force-color-profile=srgb', '--font-render-hinting=none'])
        pg = await b.new_page(viewport={'width': 1080, 'height': 1920})
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        await pg.add_init_script('window.DATA = ' + json.dumps(job) + ';')
        await pg.goto((HERE / 'coin.html').as_uri())
        await pg.wait_for_function('window.READY === true', timeout=60000)
        dur = await pg.evaluate('window.DURATION'); cues = await pg.evaluate('window.CUES')
        # QA: nothing may overflow the 1080px frame at its key moments
        qa = []
        for t in (2.2, 4.5, 6.5, 9.0, 12.0, 15.0, 17.5, 19.2, 21.5):
            await pg.evaluate(f'seek({t})')
            bad = await pg.evaluate('''[...document.querySelectorAll('#cap .l,#name1,#ename,#eurl,.why b,#post .tx')].filter(e=>getComputedStyle(e).opacity>.05).filter(e=>{const r=e.getBoundingClientRect();return r.right>1082||r.left<-2||e.scrollWidth>e.clientWidth+4}).map(e=>e.id||e.className)''')
            if bad: qa.append({'t': t, 'overflow': bad})
        if STILLS:
            for t in (1.6, 4.5, 6.5, 9.2, 12.0, 15.0, 19.2, 21.8):
                await pg.evaluate(f'seek({t})'); await pg.screenshot(path=f'{out}-{t:05.2f}.jpg', type='jpeg', quality=82)
            await b.close(); return dur, cues, qa, errs
        cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', str(FPS), '-c:v', 'mjpeg', '-i', '-',
               '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out + '.video.mp4']
        ff = subprocess.Popen(cmd, stdin=subprocess.PIPE); n = int(FPS * dur); t0 = time.time()
        for i in range(n):
            await pg.evaluate(f'seek({i / FPS})'); ff.stdin.write(await pg.screenshot(type='jpeg', quality=92))
            if i % 90 == 0: print(f'frame {i}/{n} {time.time() - t0:.0f}s', flush=True)
        ff.stdin.close(); ff.wait(); await b.close()
        return dur, cues, qa, errs

dur, cues, qa, errs = asyncio.run(frames())
report = {'slug': job.get('slug'), 'mood': MOOD, 'qa_overflow': qa, 'page_errors': errs}
if not STILLS:
    json.dump(cues, open(out + '.cues.json', 'w'))
    subprocess.run([sys.executable, str(HERE / 'score.py'), out + '.wav', MOOD, str(dur), out + '.cues.json'], check=True)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', out + '.video.mp4', '-i', out + '.wav', '-c:v', 'copy',
                    '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-shortest', '-movflags', '+faststart', out], check=True)
    # QA: loudness + black frames
    r = subprocess.run(['ffmpeg', '-i', out, '-af', 'ebur128', '-f', 'null', '-'], capture_output=True, text=True).stderr
    li = [l for l in r.splitlines() if l.strip().startswith('I:')]
    report['lufs'] = li[-1].split()[1] if li else None
    bd = subprocess.run(['ffmpeg', '-i', out, '-vf', 'blackdetect=d=0.3:pix_th=0.05', '-an', '-f', 'null', '-'], capture_output=True, text=True).stderr
    report['black_segments'] = bd.count('black_start')
    report['bytes'] = os.path.getsize(out)
    for f in (out + '.video.mp4', out + '.wav', out + '.cues.json'): os.remove(f)
report['ok'] = not qa and not errs and (STILLS or report.get('black_segments', 0) == 0)
json.dump(report, open(out + '.qa.json', 'w'), indent=1); print(json.dumps(report))
