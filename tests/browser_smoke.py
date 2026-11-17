"""Optional Firefox UI smoke test, seeded data only. Writes docs/images captures.

Install: pip install -e '.[dev,browser]'; requires Firefox on Linux.
Run: python tests/browser_smoke.py
"""
import base64
import datetime as dt
import http.client
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import urlopen
import wave

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
import websocket
import socket
import uvicorn
from app.config import Settings
from app.main import create_app
from app.infrastructure.database import Database
from app.models import Coverage
from sqlalchemy.dialects.sqlite import insert

with tempfile.TemporaryDirectory(prefix='bark-docs-') as scratch:
    data = Path(scratch)
    (data / 'recordings').mkdir()
    (data / 'logs').mkdir()
    today = dt.date.today()
    for ago, count in enumerate([34, 21, 47, 18, 29, 53, 38]):
        date = today - dt.timedelta(days=ago)
        lines=['=== BARK LOGGER SESSION ===']
        for i in range(count):
            hour=[8,8,9,12,14,17,17,18,19][i%9]
            lines.append(f'[BARKING DETECTED] {date} {hour:02}:12:{i%60:02} detected (volume: 0.0420)')
        for i, seconds in enumerate([18, 21, 15] if ago == 0 else [count*3.2, count*2.7, count*1.8]):
            lines.append(f'[BARK SESSION] From {date} {8+i*3:02}:12:00 to {date} {8+i*3:02}:15:00 (Duration: {seconds:.1f} seconds, {count//3} barks)')
        (data/'logs'/f'bark_log_{date}.txt').write_text('\n'.join(lines)+'\n')
    for clock, seconds in [('08-12-04',82),('12-34-18',106),('17-08-42',74)]:
        with wave.open(str(data/'recordings'/f'bark_audio_{today}_{clock}.wav'),'wb') as file:
            file.setnchannels(1);file.setsampwidth(2);file.setframerate(16000)
            file.writeframes(b'\0\0'*16000*seconds)
    from app.services.monitoring import DetectorMonitor
    monitor=DetectorMonitor(data)
    monitor.processed(time.time(),1.2)
    for ago in range(7):
        day=(today-dt.timedelta(days=ago)).isoformat()
        for hour in (8,9,12,14,17,18):
            with monitor.database.session.begin() as session:
                statement=insert(Coverage).values(date=day,hour=hour,seconds=3600)
                session.execute(statement.on_conflict_do_update(index_elements=['date','hour'],set_={'seconds':3600}))
    monitor.close()
    listener=socket.socket()
    listener.bind(('127.0.0.1',0))
    listener.listen()
    app=create_app(Settings(_env_file=None,data_dir=data,dashboard_pin='2468'))
    server=uvicorn.Server(uvicorn.Config(app,log_level='error'))
    thread=threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True)
    thread.start()
    base=f'http://127.0.0.1:{listener.getsockname()[1]}'
    deadline=time.monotonic()+15
    while not server.started:
        if time.monotonic()>deadline: raise RuntimeError('Server startup timed out')
        time.sleep(.1)
    profile=data/'browser'
    profile.mkdir()
    (profile/'user.js').write_text('user_pref("browser.shell.checkDefaultBrowser", false);\nuser_pref("datareporting.healthreport.uploadEnabled", false);\n')
    debug_socket=socket.socket()
    debug_socket.bind(('127.0.0.1',0))
    debug_port=debug_socket.getsockname()[1]
    debug_socket.close()
    log=open(data/'firefox.log','w')
    browser=subprocess.Popen([shutil.which('firefox') or 'firefox','--headless','--no-remote','--profile',str(profile),'--remote-debugging-port',str(debug_port),'about:blank'],stdout=log,stderr=log,start_new_session=True)
    ws=None
    try:
        deadline=time.monotonic()+30
        while True:
            try:
                ws=websocket.create_connection(f'ws://127.0.0.1:{debug_port}/session',timeout=15,suppress_origin=True)
                break
            except Exception:
                if time.monotonic()>deadline: raise RuntimeError('Firefox startup timed out; see /tmp/bark-firefox-capture.log')
                time.sleep(.3)
        serial=0
        javascript_errors=[]
        def call(method,params=None):
            global serial
            serial+=1
            request_id=serial
            ws.send(json.dumps(dict(id=request_id,method=method,params=params or {})))
            while True:
                result=json.loads(ws.recv())
                if result.get('method')=='log.entryAdded':
                    entry=result.get('params',{})
                    if entry.get('type')=='javascript' and entry.get('level')=='error':
                        javascript_errors.append(entry)
                if result.get('id')==request_id:
                    if result.get('type')=='error': raise RuntimeError(result)
                    return result.get('result',{})
        call('session.new',dict(capabilities={}))
        call('session.subscribe',dict(events=['log.entryAdded']))
        context=call('browsingContext.getTree')['contexts'][0]['context']
        def evaluate(expression):
            result=call('script.evaluate',dict(expression=expression,target=dict(context=context),awaitPromise=True))
            if result.get('type')=='exception': raise RuntimeError(result)
            return result.get('result',{}).get('value')
        def wait_for(expression):
            end=time.monotonic()+15
            while not evaluate(expression):
                if time.monotonic()>end: raise RuntimeError('Page did not become ready: '+expression)
                time.sleep(.2)
        def capture(name):
            assert evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Page overflows mobile viewport'
            result=call('browsingContext.captureScreenshot',dict(context=context,origin='viewport'))
            (PROJECT/'docs/images'/name).write_bytes(base64.b64decode(result['data']))
            print('Captured:',name,flush=True)
        call('browsingContext.setViewport',dict(context=context,viewport=dict(width=430,height=1080),devicePixelRatio=1))
        call('browsingContext.navigate',dict(context=context,url=base+'/login',wait='complete'))
        wait_for("!!document.querySelector('#login-form')")
        evaluate('document.fonts.ready.then(()=>true)')
        capture('login-mobile.png')
        status=evaluate("fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin:'2468'})}).then(r=>r.status)")
        assert status==200,status
        call('browsingContext.navigate',dict(context=context,url=base+'/',wait='complete'))
        wait_for("document.querySelector('#status')?.textContent.startsWith('Mis à jour')")
        assert evaluate("document.querySelectorAll('#recordings audio').length")==3
        evaluate("window.savedPlayer=document.querySelector('audio');window.savedPlayer.currentTime=2;document.querySelector('bark-dashboard').refresh()")
        wait_for("document.querySelector('#status').textContent.startsWith('Mis à jour')")
        assert evaluate("document.querySelector('audio')===window.savedPlayer"), 'Refresh replaced player'

        height=evaluate("Math.ceil(document.querySelector('.activity').getBoundingClientRect().bottom+window.scrollY+16)")
        call('browsingContext.setViewport',dict(context=context,viewport=dict(width=430,height=height),devicePixelRatio=1))
        capture('dashboard-mobile.png')
        call('browsingContext.setViewport',dict(context=context,viewport=dict(width=430,height=740),devicePixelRatio=1))
        evaluate("document.querySelector('#recordings').closest('section').scrollIntoView({block:'start'})")
        time.sleep(.2)
        evaluate("document.querySelectorAll('audio').forEach(audio=>{audio.preload='metadata';audio.load();})")
        wait_for("[...document.querySelectorAll('audio')].every(audio=>Number.isFinite(audio.duration))")
        capture('recordings-mobile.png')
        height=evaluate("Math.ceil(document.querySelector('.trends').nextElementSibling.getBoundingClientRect().bottom-document.querySelector('.trends').getBoundingClientRect().top+16)")
        call('browsingContext.setViewport',dict(context=context,viewport=dict(width=430,height=height),devicePixelRatio=1))
        evaluate("document.querySelector('.trends').scrollIntoView({block:'start'})")
        time.sleep(.2)
        capture('trends-mobile.png')
        evaluate('document.querySelector(\'[data-period="30"]\').click()')
        wait_for("document.querySelectorAll('.daily-column').length===30")
        assert evaluate("document.querySelectorAll('.heat-cell').length")==720
        evaluate("document.querySelector('.heat-cell').click()")
        assert evaluate("document.querySelector('#heat-detail').textContent.includes('donnée')")
        assert evaluate("document.querySelector('.metrics').textContent.includes('Extraits avec aboiements')")
        assert evaluate("document.querySelector('.metrics').textContent.includes('Séries d’aboiements')")
        assert evaluate("document.querySelector('.metric-help')===null")
        assert evaluate("document.querySelector('#detector-status').textContent.includes('Microphone à l’écoute')")
        assert evaluate("document.querySelector('#listening-summary').textContent.includes('6 h')")
        call('browsingContext.setViewport',dict(context=context,viewport=dict(width=360,height=900),devicePixelRatio=1))
        assert evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        assert evaluate("import('/static/js/shared/format.js').then(({duration})=>duration(119.9)==='2 min' && duration(3661)==='1 h 1 min')")
        # Check wording for a day with no listening data.
        evaluate("document.querySelector('#date').value='2026-01-01';document.querySelector('bark-dashboard').refresh()")
        wait_for("document.querySelector('#detections').textContent==='—'")
        assert evaluate("document.querySelector('#activity-note').textContent.includes('Aucune donnée')")
        evaluate("fetch('/api/logout',{method:'POST'}).then(r=>r.ok)")
        call('browsingContext.navigate',dict(context=context,url=base+'/login?expired=1',wait='complete'))
        assert evaluate("document.querySelector('#login-message').textContent.includes('expiré')")
        evaluate("document.querySelector('#pin').value='0000';document.querySelector('#login-form').requestSubmit()")
        wait_for("document.querySelector('#login-message').textContent.includes('Code incorrect')")
        assert evaluate("document.querySelector('#login-button').disabled")
        wait_for("!document.querySelector('#login-button').disabled")
        evaluate("document.querySelector('#pin').value='2468';document.querySelector('#login-form').requestSubmit()")
        wait_for("document.querySelector('#status')?.textContent.startsWith('Mis à jour')")
        call('browsingContext.navigate',dict(context=context,url=base+'/',wait='complete'))
        wait_for("document.querySelector('#status')?.textContent.startsWith('Mis à jour')")
        evaluate("window.originalFetch=window.fetch;window.fetch=()=>Promise.reject(new Error('Network unavailable'));document.querySelector('bark-dashboard').refresh()")
        wait_for("document.querySelector('#detector-status').dataset.state==='unknown'")
        evaluate("window.fetch=window.originalFetch")
        print('Detector UI: live status, listening duration, removed help, offline state verified.',flush=True)
        print('Login messages: expired session and wrong-code countdown verified.',flush=True)
        assert not javascript_errors, javascript_errors
        print('Mobile checks: 7/30-day switch, heatmap detail, audio players, no page overflow.',flush=True)
    finally:
        if ws: ws.close()
        os.killpg(browser.pid,signal.SIGTERM)
        try: browser.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(browser.pid,signal.SIGKILL);browser.wait()
        log.close()
        server.should_exit=True
        thread.join(timeout=10)
        listener.close()
