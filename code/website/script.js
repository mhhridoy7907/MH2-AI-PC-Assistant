

        const APPS_SCRIPT_URL = "https://script.**********************Jjeg/exec";

        /* ================= helpers ================= */
        const $ = id => document.getElementById(id);
        const TAU = Math.PI * 2;
        const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
        const lerp = (a, b, t) => a + (b - a) * t;
        const rnd = (a, b) => a + Math.random() * (b - a);
        const smooth = (cur, tar, rate, dt) => cur + (tar - cur) * (1 - Math.exp(-rate * dt));
        const ease = x => { x = clamp(x, 0, 1); return x * x * (3 - 2 * x); };
        const CYAN = [0, 235, 255], GREEN = [60, 255, 164], WHITE = [225, 250, 255];
        const mixc = (a, b, t) => { t = clamp(t, 0, 1); return [Math.round(a[0] + (b[0] - a[0]) * t), Math.round(a[1] + (b[1] - a[1]) * t), Math.round(a[2] + (b[2] - a[2]) * t)]; };
        const rgb = c => `rgb(${c[0]},${c[1]},${c[2]})`;
        const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
        const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

        if (!CanvasRenderingContext2D.prototype.roundRect) {
            CanvasRenderingContext2D.prototype.roundRect = function (x, y, w, h, r) {
                r = Math.min(Array.isArray(r) ? r[0] : r, w / 2, h / 2);
                this.moveTo(x + r, y); this.arcTo(x + w, y, x + w, y + h, r); this.arcTo(x + w, y + h, x, y + h, r);
                this.arcTo(x, y + h, x, y, r); this.arcTo(x, y, x + w, y, r); this.closePath();
            };
        }

        const S = { t: 0, dt: 0.016, active: false, voice: false, act: 0, level: 0, px: -1, py: -1, booting: true, status: 'BOOTING INTERFACE', statusAt: 0, statusUntil: 0, fps: 60, nodes: 0, rebootFlag: 0 };
        addEventListener('pointermove', e => { S.px = e.clientX; S.py = e.clientY; }, { passive: true });
        addEventListener('pointerleave', () => { S.px = -1; S.py = -1; });

        (() => {
            const cv = $('bg'), c = cv.getContext('2d');
            const CH = '01ABCDEF<>/|+-:=#';
            let w = 0, h = 0, dpr = 1, cols = [], parts = [], shooters = [], sky = [], nextStar = 0, band = 0, par = 0, parY = 0;
            const rch = () => CH[Math.floor(Math.random() * CH.length)];
            const STAR_TINTS = [[255, 255, 255], [190, 240, 255], [150, 215, 255], [190, 255, 235], [255, 240, 200]];

            function makeSky() {
                const n = clamp(Math.round(w * h / 4200), 110, 460);
                sky = Array.from({ length: n }, () => {
                    const z = Math.pow(Math.random(), 1.6) * .8 + .2;         
                    return {
                        x: rnd(0, w), y: rnd(0, h), z,
                        r: z * rnd(.5, 1.5), ph: rnd(0, TAU), sp: rnd(.7, 3),
                        tint: STAR_TINTS[Math.floor(Math.random() * STAR_TINTS.length)],
                        big: z > .72 && Math.random() < .22                     
                    };
                });
            }

            function init(keep) {
                dpr = Math.min(devicePixelRatio || 1, 2);
                w = innerWidth; h = innerHeight;
                cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
                c.setTransform(dpr, 0, 0, dpr, 0, 0);
                makeSky();
                const n = Math.max(8, Math.floor(w / (w < 700 ? 34 : 42)));
                cols = Array.from({ length: n }, (_, i) => { const len = 7 + Math.floor(Math.random() * 9); return { x: (i + Math.random() * .8) * (w / n), y: rnd(-h, h), v: rnd(35, 110), len, ch: Array.from({ length: len }, rch) }; });
                const pn = clamp(Math.round(w * h / (w < 700 ? 13000 : 11000)), 38, 100);
                if (!keep || !parts.length) parts = Array.from({ length: pn }, () => ({ x: rnd(0, w), y: rnd(0, h), vx: rnd(-18, 18), vy: rnd(-13, 13), r: [1, 1, 2][Math.floor(Math.random() * 3)], ph: rnd(0, TAU) }));
                else { while (parts.length > pn) parts.pop(); while (parts.length < pn) parts.push({ x: rnd(0, w), y: rnd(0, h), vx: rnd(-18, 18), vy: rnd(-13, 13), r: 1, ph: rnd(0, TAU) }); }
                S.nodes = parts.length;
            }
            let lastW = 0, lastH = 0;
            addEventListener('resize', () => { if (innerWidth !== lastW || Math.abs(innerHeight - lastH) > 160) { lastW = innerWidth; lastH = innerHeight; init(true); } });
            lastW = innerWidth; lastH = innerHeight; init();
            S.regenBg = () => init(false);

            function drawSky(t, dt, act) {

                const tx = S.px >= 0 ? (S.px / w - .5) : 0, ty = S.py >= 0 ? (S.py / h - .5) : 0;
                par = smooth(par, tx, 2.5, dt); parY = smooth(parY, ty, 2.5, dt);
                const sc = (scrollY || 0) * .05;
                for (const s of sky) {
                    let x = (s.x + t * 5 * s.z - par * 60 * s.z) % w; if (x < 0) x += w;
                    let y = (s.y + t * 2 * s.z - parY * 40 * s.z - sc * s.z) % h; if (y < 0) y += h;
                    const tw = .5 + .5 * Math.sin(t * s.sp + s.ph);
                    const a = clamp((.25 + .75 * tw) * (.35 + .65 * s.z) * (1 + .25 * act), 0, 1);
                    const col = act > .5 ? mixc(s.tint, [190, 255, 225], act * .5) : s.tint;
                    if (s.big) {
                        const gl = s.r * (7 + 4 * tw);
                        const g = c.createRadialGradient(x, y, 0, x, y, gl);
                        g.addColorStop(0, rgba(col, .55 * a)); g.addColorStop(1, rgba(col, 0));
                        c.fillStyle = g; c.fillRect(x - gl, y - gl, gl * 2, gl * 2);
                        const L = s.r * (6 + 6 * tw);
                        c.strokeStyle = rgba(col, .55 * a); c.lineWidth = .8;
                        c.beginPath(); c.moveTo(x - L, y); c.lineTo(x + L, y); c.moveTo(x, y - L); c.lineTo(x, y + L); c.stroke();
                    }
                    c.fillStyle = rgba(col, a);
                    c.beginPath(); c.arc(x, y, Math.max(.45, s.r * (.8 + .3 * tw)), 0, TAU); c.fill();
                }
            }

            function frame() {
                const dt = S.dt, t = S.t, act = S.act;
                c.fillStyle = '#030810'; c.fillRect(0, 0, w, h);
                const col = mixc(CYAN, GREEN, act);


                drawSky(t, dt, act);


                c.font = '12px ui-monospace,Consolas,monospace'; c.textBaseline = 'top';
                for (const k of cols) {
                    k.y += k.v * dt * (1 + .8 * act);
                    if (k.y - k.len * 14 > h) { k.y = rnd(-200, 0); k.v = rnd(35, 110); }
                    if (Math.random() < dt * 9) k.ch[Math.floor(Math.random() * k.len)] = rch();
                    for (let j = 0; j < k.len; j++) {
                        const y = k.y - j * 14; if (y < -14 || y > h) continue;
                        const f = 1 - j / k.len;
                        c.fillStyle = j === 0 ? rgba(mixc(col, WHITE, .5), .45) : rgba(col, .04 + .15 * f * f);
                        c.fillText(k.ch[j], k.x, y);
                    }
                }


                band = ((t * 55) % (h + 160)) - 80;
                const g = c.createLinearGradient(0, band - 25, 0, band + 25);
                g.addColorStop(0, 'rgba(0,235,255,0)'); g.addColorStop(.5, 'rgba(0,235,255,.06)'); g.addColorStop(1, 'rgba(0,235,255,0)');
                c.fillStyle = g; c.fillRect(0, band - 25, w, 50);


                const sp = 1 + .6 * act;
                for (const p of parts) {
                    p.x += p.vx * dt * sp; p.y += p.vy * dt * sp;
                    if (p.x < 0) p.x = w; else if (p.x > w) p.x = 0;
                    if (p.y < 0) p.y = h; else if (p.y > h) p.y = 0;
                }
                const lim = w < 700 ? 90 : 105, lim2 = lim * lim;
                c.lineWidth = 1;
                for (let i = 0; i < parts.length; i++) {
                    const p = parts[i];
                    for (let j = i + 1; j < parts.length; j++) {
                        const q = parts[j], dx = p.x - q.x, dy = p.y - q.y, d2 = dx * dx + dy * dy;
                        if (d2 < lim2) { c.strokeStyle = rgba(col, (1 - d2 / lim2) * .26); c.beginPath(); c.moveTo(p.x, p.y); c.lineTo(q.x, q.y); c.stroke(); }
                    }
                }

                if (S.px >= 0) {
                    const r2 = 150 * 150;
                    for (const p of parts) {
                        const dx = p.x - S.px, dy = p.y - S.py, d2 = dx * dx + dy * dy;
                        if (d2 < r2) { c.strokeStyle = rgba(col, (1 - d2 / r2) * .5); c.beginPath(); c.moveTo(p.x, p.y); c.lineTo(S.px, S.py); c.stroke(); }
                    }
                }

                for (const p of parts) {
                    const tw = .7 + .3 * Math.sin(t * 2 + p.ph);
                    if (p.r === 2) {
                        const gr = c.createRadialGradient(p.x, p.y, 0, p.x, p.y, 9);
                        gr.addColorStop(0, rgba(col, .45)); gr.addColorStop(1, rgba(col, 0));
                        c.fillStyle = gr; c.fillRect(p.x - 9, p.y - 9, 18, 18);
                        c.fillStyle = rgb(col); c.beginPath(); c.arc(p.x, p.y, 2, 0, TAU); c.fill();
                    } else { c.fillStyle = `rgba(0,${Math.round(155 + 80 * tw)},${Math.round(175 + 70 * tw)},.9)`; c.fillRect(p.x - .5, p.y - .5, 1.6, 1.6); }
                }

                if (!reduced) {
                    nextStar -= dt;
                    if (nextStar <= 0 && shooters.length < 9) {
                        nextStar = rnd(.35, 1.3);
                        const ang = rnd(.45, .85);                                
                        const spd = rnd(480, 900);
                        shooters.push({ x: rnd(w * .1, w * 1.2), y: rnd(-80, h * .4), vx: -Math.cos(ang) * spd, vy: Math.sin(ang) * spd, life: 0, max: rnd(.9, 1.7), len: rnd(110, 260), tint: Math.random() < .3 ? [160, 255, 215] : [215, 252, 255] });
                    }
                    for (let i = shooters.length - 1; i >= 0; i--) {
                        const s = shooters[i]; s.life += dt; s.x += s.vx * dt; s.y += s.vy * dt;
                        const a = Math.sin(clamp(s.life / s.max, 0, 1) * Math.PI);
                        if (s.life > s.max || s.y > h + 60 || s.x < -80) { shooters.splice(i, 1); continue; }
                        const m = Math.hypot(s.vx, s.vy), tx = s.x - s.vx / m * s.len, ty = s.y - s.vy / m * s.len;
                        const lg = c.createLinearGradient(tx, ty, s.x, s.y);
                        lg.addColorStop(0, rgba(s.tint, 0)); lg.addColorStop(.7, rgba(s.tint, .35 * a)); lg.addColorStop(1, rgba([255, 255, 255], .95 * a));
                        c.strokeStyle = lg; c.lineWidth = 1.8; c.lineCap = 'round'; c.beginPath(); c.moveTo(tx, ty); c.lineTo(s.x, s.y); c.stroke();
                        const sg = c.createRadialGradient(s.x, s.y, 0, s.x, s.y, 14);
                        sg.addColorStop(0, `rgba(255,255,255,${a})`); sg.addColorStop(.35, rgba(s.tint, .5 * a)); sg.addColorStop(1, 'rgba(0,235,255,0)');
                        c.fillStyle = sg; c.fillRect(s.x - 14, s.y - 14, 28, 28);
                    }
                    c.lineCap = 'butt';
                }
            }
            S.bgFrame = frame;
        })();

        /* ================= HUD: core, equalizer, UI ================= */
        (() => {
            const stage = $('stage'), cv = $('core'), c = cv.getContext('2d');
            const eqc = $('eq'), ec = eqc.getContext('2d');
            const spA = $('sparkA'), spB = $('sparkB');
            let w = 0, h = 0, dpr = 1;

            function sizeCanvas(cnv, cw, ch) {
                dpr = Math.min(devicePixelRatio || 1, 2);
                cnv.width = Math.max(1, Math.round(cw * dpr)); cnv.height = Math.max(1, Math.round(ch * dpr));
                const x = cnv.getContext('2d'); x.setTransform(dpr, 0, 0, dpr, 0, 0); return x;
            }
            function resize() {
                const r = stage.getBoundingClientRect(); w = r.width; h = r.height; c.setTransform(1, 0, 0, 1, 0, 0); sizeCanvas(cv, w, h);
                const er = eqc.getBoundingClientRect(); sizeCanvas(eqc, er.width, er.height);
                for (const s of [spA, spB]) { const sr = s.getBoundingClientRect(); sizeCanvas(s, sr.width, sr.height); }
                $('tDisp').textContent = innerWidth + 'x' + innerHeight;
            }
            new ResizeObserver(resize).observe(stage); addEventListener('resize', resize);


            const EQN = 41, ev = new Array(EQN).fill(0), ep = new Array(EQN).fill(0);
            function updateEq(dt, t, act, level) {
                const ctr = (EQN - 1) / 2;
                for (let i = 0; i < EQN; i++) {
                    const d = Math.abs(i - ctr) / ctr, env = 1 - .6 * d;
                    const amb = .07 + .04 * Math.sin(t * 2.2 + i * .5) + .05 * act * Math.abs(Math.sin(t * 1.7 + i * .31));
                    const live = level * env * (.35 + .65 * Math.abs(Math.sin(t * 7.5 + i * .9) * Math.cos(t * 3.3 + i * .37))) * 1.4;
                    const tar = clamp(amb + live, 0, 1);
                    ev[i] = smooth(ev[i], tar, tar > ev[i] ? 18 : 7, dt);
                    ep[i] = Math.max(ev[i], ep[i] - dt * .45);
                }
            }
            function drawEq(act) {
                const W = eqc.width / dpr, H = eqc.height / dpr; ec.clearRect(0, 0, W, H);
                const gap = 3, bw = Math.max(2, (W - (EQN - 1) * gap) / EQN), cy = H / 2;
                const dim = mixc([0, 70, 85], [20, 100, 75], act), hot = mixc(CYAN, GREEN, act);
                for (let i = 0; i < EQN; i++) {
                    const hg = Math.max(3, (H - 4) * ev[i]), x = i * (bw + gap);
                    ec.fillStyle = rgb(mixc(dim, hot, ev[i] * 1.1)); ec.beginPath(); ec.roundRect(x, cy - hg / 2, bw, hg, 2); ec.fill();
                    const cap = (H - 4) * ep[i] / 2;
                    if (cap > hg / 2 + 2) { ec.fillStyle = rgb(hot); ec.fillRect(x, cy - cap, bw, 1.5); ec.fillRect(x, cy + cap, bw, 1.5); }
                }
            }
            function drawSpark(cnv, vals, color, vmax) {
                const x = cnv.getContext('2d'), W = cnv.width / dpr, H = cnv.height / dpr; x.clearRect(0, 0, W, H);
                if (vals.length < 2) return;
                x.beginPath(); vals.forEach((v, i) => { const px = W * i / (vals.length - 1), py = H - H * clamp(v / vmax, 0, 1); i ? x.lineTo(px, py) : x.moveTo(px, py); });
                x.strokeStyle = rgb(color); x.lineWidth = 1; x.stroke(); x.lineTo(W, H); x.lineTo(0, H); x.closePath(); x.fillStyle = rgba(color, .15); x.fill();
            }


            const face = { blinkStart: null, double: false, next: 2, gx: 0, gy: 0 };
            function blink(t) {
                if (face.blinkStart === null) { if (t < face.next) return 0; face.blinkStart = t; face.double = Math.random() < .22; }
                const p = (t - face.blinkStart) / .2;
                if (p < 0) return 0;
                if (p >= 1) { if (face.double) { face.double = false; face.blinkStart = t + .07; return 0; } face.blinkStart = null; face.next = t + rnd(2.4, 5.6); return 0; }
                return Math.sin(p * Math.PI);
            }
            function glow(x, y, r, col, a) { const g = c.createRadialGradient(x, y, 0, x, y, r); g.addColorStop(0, rgba(col, a)); g.addColorStop(1, rgba(col, 0)); c.fillStyle = g; c.fillRect(x - r, y - r, r * 2, r * 2); }
            function glowDot(x, y, col, r) { glow(x, y, r * 4, col, .6); c.fillStyle = rgb(col); c.beginPath(); c.arc(x, y, r, 0, TAU); c.fill(); }
            function ring(cx, cy, r, ang, col, segs, th, frac) {
                c.strokeStyle = col; c.lineWidth = th;
                for (let i = 0; i < segs; i++) { const s = ang + i * TAU / segs; c.beginPath(); c.arc(cx, cy, r, s, s + TAU / segs * frac); c.stroke(); }
            }
            let corePos = { x: 0, y: 0, r: 0 };

            function drawCore() {
                c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, w, h);
                const t = S.t, dt = S.dt, act = S.act, color = mixc(CYAN, GREEN, act), col = rgb(color);
                const cx = w / 2, cy = h / 2, R = Math.min(h * .25, w * .2, 112);
                const r = R * (1 + .022 * Math.sin(t * lerp(1.5, 3.2, act)));
                corePos = { x: cx, y: cy, r: R + 30 };


                for (let i = 0; i < 38; i++) {
                    const sx = (Math.sin(i * 12.9898) * 43758.5453 % 1 + 1) % 1 * w, sy = (Math.sin(i * 78.233) * 12543.123 % 1 + 1) % 1 * h;
                    const a = .15 + .35 * (.5 + .5 * Math.sin(t * 1.6 + i));
                    c.fillStyle = `rgba(190,245,255,${a})`; c.fillRect(sx, sy, 1.4, 1.4);
                }

                glow(cx, cy, r + 80, mixc([0, 70, 90], [10, 110, 80], act), .5);


                const ang = t * 1.3, rad = r + 32;
                for (let i = 22; i > 0; i--) {
                    const a0 = ang - i * .045, a1 = a0 + .05, al = .3 * Math.pow(1 - i / 22, 1.6) * (.45 + .55 * act);
                    c.fillStyle = rgba(color, al); c.beginPath(); c.moveTo(cx, cy); c.arc(cx, cy, rad, a0, a1); c.closePath(); c.fill();
                }
                c.strokeStyle = rgba(color, .75); c.lineWidth = 1; c.beginPath(); c.moveTo(cx, cy); c.lineTo(cx + Math.cos(ang) * rad, cy + Math.sin(ang) * rad); c.stroke();


                for (let k = 0; k < 3; k++) {
                    const p = ((t * (.25 + .2 * act) + k / 3) % 1), pr = r + 30 + p * 70;
                    c.strokeStyle = rgba(color, (1 - p) * .28); c.lineWidth = 1.2; c.beginPath(); c.arc(cx, cy, pr, 0, TAU); c.stroke();
                }


                ring(cx, cy, r + 35, t * .22, '#55879e', 16, 1, .2);
                ring(cx, cy, r + 24, -t * .45, '#2d73ff', 8, 2, .55);
                ring(cx, cy, r + 10, t * .75, col, 5, 2, .55);
                ring(cx, cy, r - 6, -t * .4, rgb(GREEN), 3, 2, .55);

                const tr = r + 44, rot = t * .08;
                for (let i = 0; i < 72; i++) {
                    const a = rot + i * TAU / 72, major = i % 6 === 0, inn = tr - (major ? 12 : 5), ca = Math.cos(a), sa = Math.sin(a);
                    c.strokeStyle = major ? col : '#144b5a'; c.lineWidth = major ? 2 : 1;
                    c.beginPath(); c.moveTo(cx + ca * inn, cy + sa * inn); c.lineTo(cx + ca * tr, cy + sa * tr); c.stroke();
                }
                

                for (let i = 0; i < 12; i++) {
                    const base = t * .5 + i * TAU / 12, orb = r + (i % 2 ? 18 : 30);
                    for (let k = 3; k > 0; k--) { const a = base - k * .05; c.fillStyle = rgba(color, .16 * (4 - k)); c.fillRect(cx + Math.cos(a) * orb - .5, cy + Math.sin(a) * orb - .5, 1.6, 1.6); }
                    glowDot(cx + Math.cos(base) * orb, cy + Math.sin(base) * orb, i % 3 === 0 ? GREEN : color, i % 3 === 0 ? 3 : 2);
                }

                
                const fw = r * 1.1, fh = r * 1.2, fx = cx - fw / 2, fy = cy - fh / 2, rc = Math.max(14, r * .22);
                for (const side of [-1, 1]) {
                    const ew = 8, eh = r * .3, ex = side < 0 ? fx - ew - 2 : fx + fw + 2;
                    c.fillStyle = '#041520'; c.strokeStyle = rgba(color, .7); c.lineWidth = 1; c.beginPath(); c.roundRect(ex, cy - eh / 2, ew, eh, 3); c.fill(); c.stroke();
                }
                c.fillStyle = '#041520'; c.beginPath(); c.roundRect(fx, fy, fw, fh, rc); c.fill();
                c.fillStyle = '#061c2a'; c.beginPath(); c.roundRect(fx + 7, fy + 7, fw - 14, fh - 14, Math.max(10, rc - 6)); c.fill();
                c.strokeStyle = rgb(mixc([15, 75, 91], color, .2)); c.lineWidth = 1; c.beginPath(); c.roundRect(fx - 2, fy - 2, fw + 4, fh + 4, rc + 2); c.stroke();
                c.shadowColor = col; c.shadowBlur = 14; c.strokeStyle = col; c.lineWidth = 2; c.beginPath(); c.roundRect(fx, fy, fw, fh, rc); c.stroke(); c.shadowBlur = 0;
                c.strokeStyle = '#145a6c'; c.lineWidth = 1;
                for (let i = 0; i < 5; i++) { const vx = cx - 32 * (r / 112) + i * 16 * (r / 112); c.beginPath(); c.moveTo(vx, fy + 9); c.lineTo(vx + 8, fy + 9); c.stroke(); }
                const sy = fy + 18 + (fh - 36) * ((t * .4) % 1);
                c.strokeStyle = rgba(color, .3); c.beginPath(); c.moveTo(fx + 14, sy); c.lineTo(fx + fw - 14, sy); c.stroke();

                
                const bl = blink(t), open = Math.max(.06, lerp(.55, 1, act) * (1 - bl));
                const tx = S.px >= 0 ? clamp((S.px - (stage.getBoundingClientRect().left + cx)) / (innerWidth * .5), -1, 1) : 0;
                const ty = S.py >= 0 ? clamp((S.py - (stage.getBoundingClientRect().top + cy)) / (innerHeight * .5), -1, 1) : 0;
                face.gx = smooth(face.gx, tx + .25 * Math.sin(t * .7), 5, dt); face.gy = smooth(face.gy, ty * .8 + .15 * Math.sin(t * .9 + 1), 5, dt);
                const gx = face.gx * r * .06, gy = face.gy * r * .035;
                const eyeY = cy - r * .14, gap = r * .27, ew = Math.max(14, r * .27), ehm = Math.max(8, r * .16), eyeCol = mixc(color, WHITE, .1);
                for (const side of [-1, 1]) {
                    const ex = cx + side * gap;
                    c.fillStyle = '#020c14'; c.strokeStyle = '#0e3c4c'; c.lineWidth = 1; c.beginPath(); c.roundRect(ex - (ew + 14) / 2, eyeY - (ehm + 12) / 2, ew + 14, ehm + 12, 9); c.fill(); c.stroke();
                    const eh = Math.max(2, ehm * open);
                    glow(ex + gx, eyeY + gy, r * .3, mixc([0, 90, 100], [30, 130, 100], act), .7);
                    c.fillStyle = rgb(eyeCol); c.beginPath(); c.ellipse(ex + gx, eyeY + gy, ew / 2, eh / 2, 0, 0, TAU); c.fill();
                    if (eh > 6) {
                        c.fillStyle = rgb(mixc(color, WHITE, .6)); c.beginPath(); c.ellipse(ex + gx, eyeY + gy, ew * .3, eh * .3, 0, 0, TAU); c.fill();
                        c.fillStyle = '#fff'; c.beginPath(); c.arc(ex + gx - ew / 5, eyeY + gy - eh / 5, 2, 0, TAU); c.fill();
                    }
                    const by = eyeY - ehm - 12, tilt = lerp(1, 4, act);
                    c.strokeStyle = rgba(color, .8); c.lineWidth = 2; c.beginPath(); c.moveTo(ex - ew * .6, by + side * tilt); c.lineTo(ex + ew * .6, by - side * tilt); c.stroke();
                }
                
                const my = cy + r * .27, bars = 11, bw = Math.max(3, r * .035), mg = Math.max(2, r * .025), tot = bars * bw + (bars - 1) * mg, sx = cx - tot / 2, lv = S.level;
                glow(cx, my, r * (.28 + .22 * lv), mixc([0, 70, 80], [20, 100, 70], act), .6);
                c.fillStyle = col;
                for (let i = 0; i < bars; i++) {
                    const d = Math.abs(i - (bars - 1) / 2) / ((bars - 1) / 2), env = 1 - .7 * d;
                    const wave = Math.abs(Math.sin(t * 9 + i * .8)) * .6 + Math.abs(Math.sin(t * 5.3 + i * 1.7)) * .4;
                    let hg = 2 + 1.5 * Math.abs(Math.sin(t * 2 + i * .5)) * (.4 + act); hg += r * .16 * lv * env * wave * 1.3;
                    c.fillRect(sx + i * (bw + mg), my - hg / 2, bw, hg);
                }
                
                const phase = Math.floor(t * 2.5) % 3;
                for (let i = 0; i < 3; i++) {
                    const x = cx - 14 + i * 14, y = cy + r * .46, on = S.active && phase === i;
                    if (on) glowDot(x, y, color, 2); else { c.fillStyle = '#0e3c4c'; c.beginPath(); c.arc(x, y, 2, 0, TAU); c.fill(); }
                }
            }

            
            const logs = [];
            const stamp = () => new Date().toLocaleTimeString('en-GB');
            function log(msg) { logs.push([stamp(), msg]); if (logs.length > 40) logs.shift(); renderLog(); }
            function renderLog() {
                const el = $('log'); el.textContent = '';
                logs.slice(-6).forEach(([ts, m]) => { const p = document.createElement('p'); p.textContent = ts + ' ' + m; el.appendChild(p); });
            }
            function setStatus(msg, dur = 2.6) { S.status = msg; S.statusAt = S.t; S.statusUntil = dur ? S.t + dur : 0; }
            const idle = () => S.active ? 'AI CORE READY' : S.voice ? 'VOICE VISUALIZER ACTIVE' : 'SYSTEM STANDBY';
            function refresh() {
                $('bAiT').textContent = S.active ? 'AI: ONLINE' : 'ACTIVATE AI'; $('bAi').classList.toggle('sel', S.active);
                $('bVoiceT').textContent = S.voice ? 'VOICE: ON' : 'VOICE MODE'; $('bVoice').classList.toggle('sel', S.voice);
                $('sCore').textContent = S.active ? 'ACTIVE' : 'STANDBY'; $('sCore').className = S.active ? 'g' : '';
                $('sVoice').textContent = S.voice ? 'ACTIVE' : 'STANDBY'; $('sVoice').className = S.voice ? 'g' : '';
                $('hdrState').textContent = S.active ? 'AI ACTIVE' : 'SYSTEM STANDBY'; $('hdrState').classList.toggle('on', S.active);
                $('link').textContent = S.active ? 'ACTIVE' : S.voice ? 'LISTENING' : 'STANDBY';
            }
            function toggleAi() { S.active = !S.active; setStatus(S.active ? 'AI CORE ACTIVATED' : 'SYSTEM STANDBY'); log('AI STATE: ' + (S.active ? 'ACTIVE' : 'STANDBY')); refresh(); }
            function toggleVoice() { S.voice = !S.voice; setStatus(S.voice ? 'VOICE VISUALIZER ACTIVE' : 'VOICE MODE DISABLED'); log('VOICE MODE: ' + (S.voice ? 'ON' : 'OFF')); refresh(); }
            function reboot() { S.active = false; S.voice = false; S.regenBg(); face.blinkStart = null; ev.fill(0); ep.fill(0); log('SYSTEM REBOOT'); refresh(); boot(); }
            $('bAi').onclick = toggleAi; $('bVoice').onclick = toggleVoice; $('bReboot').onclick = reboot;
            addEventListener('keydown', e => {
                if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName) || e.ctrlKey || e.metaKey || e.altKey) return;
                if (e.code === 'Space') { e.preventDefault(); toggleAi(); }
                else if (e.key.toLowerCase() === 'v') toggleVoice();
                else if (e.key.toLowerCase() === 'r') reboot();
            });
            cv.addEventListener('click', e => { const r = cv.getBoundingClientRect(); if (Math.hypot(e.clientX - r.left - corePos.x, e.clientY - r.top - corePos.y) <= corePos.r) toggleAi(); });
            cv.addEventListener('pointermove', e => { const r = cv.getBoundingClientRect(); cv.style.cursor = Math.hypot(e.clientX - r.left - corePos.x, e.clientY - r.top - corePos.y) <= corePos.r ? 'pointer' : 'default'; });

            
            let bootT0 = 0, bootQ = [];
            function boot() {
                S.booting = true; bootT0 = S.t; setStatus('BOOTING INTERFACE', 0);
                bootQ = [[.25, 'DISPLAY CONTEXT READY'], [.8, 'RENDER PIPELINE ONLINE'], [1.3, 'BACKEND NOT CONNECTED'], [1.8, 'INTERFACE READY']];
                const b = $('boot'); b.classList.remove('done'); b.style.display = 'flex';
                if (reduced) { bootT0 = S.t - 10; }
            }
            function updateBoot() {
                if (!S.booting) return;
                const bt = S.t - bootT0;
                while (bootQ.length && bt >= bootQ[0][0]) log(bootQ.shift()[1]);
                const p = clamp(bt / 2, 0, 1); $('bootFill').style.width = p * 100 + '%'; $('bootPct').textContent = Math.round(p * 100) + '%';
                if (bt > .9) $('boot').classList.add('done');
                if (bt >= 2.4) { S.booting = false; $('boot').style.display = 'none'; setStatus(idle(), 0); }
            }
            
            const hw = $('hudWave'); for (let i = 0; i < 28; i++) hw.appendChild(document.createElement('i'));
            const hwBars = [...hw.children];

            const frameHist = [], lvHist = [];
            let fpsAcc = 0, fpsN = 0, uiTimer = 0, lastStatusShown = '';

            function update() {
                const dt = S.dt, t = S.t;
                S.act = smooth(S.act, S.active ? 1 : 0, 4, dt);
                const target = S.voice ? .5 + .28 * Math.sin(t * 2.3) * Math.sin(t * .7 + 1) : 0;
                S.level = smooth(S.level, target, 10, dt);
                frameHist.push(dt * 1000); if (frameHist.length > 70) frameHist.shift();
                lvHist.push(S.level); if (lvHist.length > 70) lvHist.shift();
                updateBoot();
                if (!S.booting && S.statusUntil && t > S.statusUntil) { S.status = idle(); S.statusAt = t; S.statusUntil = 0; }
                updateEq(dt, t, S.act, S.level);

                
                const full = S.status, shown = Math.floor((t - S.statusAt) * 55) + 1;
                const part = full.slice(0, shown) + (shown <= full.length && Math.floor(t * 6) % 2 === 0 ? '_' : '');
                if (part !== lastStatusShown) { $('statusText').textContent = part; lastStatusShown = part; }

                
                fpsAcc += dt; fpsN++; uiTimer += dt;
                if (uiTimer > .25) {
                    S.fps = fpsN / fpsAcc; fpsAcc = 0; fpsN = 0; uiTimer = 0;
                    const up = Math.floor(t);
                    $('tFps').textContent = S.fps.toFixed(0); $('tFps').className = S.fps >= 50 ? 'g' : 'o';
                    $('tFrame').textContent = dt * 1000 < 100 ? (1000 / Math.max(S.fps, 1)).toFixed(1) + ' ms' : '—';
                    $('tUp').textContent = String(Math.floor(up / 60)).padStart(2, '0') + ':' + String(up % 60).padStart(2, '0');
                    $('tNodes').textContent = S.nodes; $('clock').textContent = stamp();
                    $('fpsFoot').textContent = S.fps.toFixed(0) + ' FPS | ' + innerWidth + 'x' + innerHeight;
                    $('temp').textContent = (36.4 + S.act * 4.2 + Math.sin(t) * .3).toFixed(1) + '°C';
                }
                
                const m = .3 + .7 * Math.max(S.act, S.level);
                hwBars.forEach((b, i) => { const v = .25 + .75 * Math.abs(Math.sin(t * 2.4 + i * .5) * Math.cos(t * 1.1 + i * .21)) * m; b.style.height = Math.max(2, 24 * v) + 'px'; b.style.background = rgb(mixc([0, 70, 85], mixc(CYAN, GREEN, S.act), v)); });
            }

            
            let last = performance.now();
            function loop(now) {
                S.dt = Math.min((now - last) / 1000, .05) || .016; last = now;
                S.t += reduced ? S.dt * .3 : S.dt;
                S.bgFrame(); update();
                if (w) drawCore();
                drawEq(S.act);
                drawSpark(spA, frameHist, CYAN, Math.max(20, ...frameHist));
                drawSpark(spB, lvHist, mixc(CYAN, GREEN, S.act), 1);
                requestAnimationFrame(loop);
            }

            $('year').textContent = new Date().getFullYear();
            resize(); refresh(); boot();
            requestAnimationFrame(t0 => { last = t0; requestAnimationFrame(loop); });
        })();

        

        const navLinks = $('navLinks'), menuBtn = $('menuBtn');
        menuBtn.addEventListener('click', () => { const o = navLinks.classList.toggle('open'); menuBtn.setAttribute('aria-expanded', String(o)); menuBtn.textContent = o ? '✕' : '☰'; });
        navLinks.querySelectorAll('a').forEach(a => a.addEventListener('click', () => { navLinks.classList.remove('open'); menuBtn.setAttribute('aria-expanded', 'false'); menuBtn.textContent = '☰'; }));

        const progress = $('progress'), navWrap = $('navWrap');
        const sectionLinks = [...navLinks.querySelectorAll('a[href^="#"]')].map(a => ({ a, el: document.querySelector(a.getAttribute('href')) })).filter(x => x.el);
        function onScroll() {
            const max = document.documentElement.scrollHeight - innerHeight;
            progress.style.width = (max > 0 ? scrollY / max * 100 : 0) + '%';
            navWrap.classList.toggle('scrolled', scrollY > 20);
            let cur = null; const y = scrollY + innerHeight * .35;
            for (const s of sectionLinks) if (s.el.offsetTop <= y) cur = s;
            sectionLinks.forEach(s => s.a.classList.toggle('act', s === cur));
        }
        addEventListener('scroll', onScroll, { passive: true }); onScroll();

        
        const cg = $('cursorGlow');
        if (cg && matchMedia('(pointer:fine)').matches) {
            let gx = -999, gy = -999, tx = -999, ty = -999;
            addEventListener('pointermove', e => { tx = e.clientX; ty = e.clientY; }, { passive: true });
            (function tick() { gx += (tx - gx) * .12; gy += (ty - gy) * .12; cg.style.left = gx + 'px'; cg.style.top = gy + 'px'; requestAnimationFrame(tick); })();
        }

        
        const io = 'IntersectionObserver' in window ? new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }), { threshold: .12 }) : null;
        document.querySelectorAll('.grid, .about-grid').forEach(g => [...g.children].forEach((el, i) => { if (el.classList.contains('reveal')) el.style.transitionDelay = (i % 3) * 120 + 'ms'; }));
        document.querySelectorAll('.reveal').forEach(el => io ? io.observe(el) : el.classList.add('in'));

        
        const canTilt = matchMedia('(pointer:fine)').matches && !reduced;
        document.querySelectorAll('.card').forEach(card => {
            const move = e => {
                const r = card.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
                card.style.setProperty('--mx', x + 'px'); card.style.setProperty('--my', y + 'px');
                if (canTilt && e.pointerType === 'mouse' && card.classList.contains('in')) {
                    const rx = ((y / r.height) - .5) * -6, ry = ((x / r.width) - .5) * 6;
                    card.style.transition = 'transform .12s ease-out, border-color .3s, box-shadow .3s, opacity .8s';
                    card.style.transform = `perspective(900px) rotateX(${rx}deg) rotateY(${ry}deg) translateY(-3px)`;
                }
            };
            card.addEventListener('pointermove', move); card.addEventListener('pointerdown', move);
            card.addEventListener('pointerleave', () => { card.style.transition = ''; card.style.transform = ''; });
        });
        
        document.querySelectorAll('.purchase-btn').forEach(btn => btn.addEventListener('click', () => {
            $('requestType').value = 'MH2 AI Purchase';
            $('subject').value = `Purchase request — ${btn.dataset.version} ($50 USD)`;
            $('message').value = `I would like to request access to MH2 AI PC Assistant for ${btn.dataset.version}. Please share the payment and delivery instructions.`;
            $('contact').scrollIntoView({ behavior: 'smooth' });
            setTimeout(() => $('firstName').focus({ preventScroll: true }), 450);
        }));

        const form = $('contactForm'), statusBox = $('formStatus'), submitBtn = $('submitBtn');
        function showStatus(m, k) { statusBox.textContent = m; statusBox.className = 'form-status show ' + k; }
        form.addEventListener('submit', async ev => {
            ev.preventDefault();
            if (!form.reportValidity()) return;
            if ($('website').value) return; 
            if (!APPS_SCRIPT_URL.startsWith('https://script.google.com/macros/s/') || !APPS_SCRIPT_URL.endsWith('/exec')) {
                showStatus('Setup required: add your deployed Google Apps Script Web App /exec URL in index.html before submitting. No request has been sent.', 'err'); return;
            }
            const data = Object.fromEntries(new FormData(form).entries());
            data.pageUrl = location.href; data.userAgent = navigator.userAgent;
            submitBtn.disabled = true; submitBtn.textContent = 'Sending…'; showStatus('Sending your request securely…', 'info');
            try {
                const res = await fetch(APPS_SCRIPT_URL, { method: 'POST', headers: { 'Content-Type': 'text/plain;charset=utf-8' }, body: JSON.stringify(data), redirect: 'follow' });
                const result = await res.json();
                if (!res.ok || !result || result.success !== true) throw new Error(result && result.message ? result.message : 'The server did not confirm the request.');
                showStatus('Request submitted successfully. The developer will contact you using the email you provided.', 'ok'); form.reset();
            } catch (err) {
                showStatus('We could not confirm submission from this browser. Your request may not have been saved. Please email mhhridoy7907@gmail.com directly. Details: ' + (err.message || 'Network error'), 'err');
            } finally { submitBtn.disabled = false; submitBtn.innerHTML = 'Send request <span aria-hidden="true">→</span>'; }
        });
