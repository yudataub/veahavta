# -*- coding: utf-8 -*-
"""
ספריית ואהבת — מעלה את קבצי האודיו מ-G: לריפואי מדיה ב-GitHub Pages ובונה את הקטלוג.
עותק מותאם של shiurim/tools/publish.py: כפילויות (שם+גודל) עולות פעם אחת, והחלוקה
לנושאים נקבעת ב-topics.py בזמן `catalog` (אפשר לשנות בלי להעלות מחדש).

למה ריפואים רבים: GitHub דוחה קובץ מעל 100MB, ואתר Pages מוגבל ל-~1GB.
לכן הקבצים נארזים ברצף לריפואים של עד PACK_BYTES (veahavta-a01, a02, ...).
GitHub Pages מגיש mp3/m4a עם Range — <audio> רגיל מנגן ומדלג (כמו ב-wa-archive).

השיוך קובץ→ריפו נשמר ב-manifest.json ולא מחושב מחדש — הוספת קבצים בעתיד
לא תזיז קבצים שכבר עלו. כל שלב אידמפוטנטי; אפשר להריץ שוב אחרי הפסקה.

  python publish.py plan            סורק את G: ומשייך קבצים חדשים לריפואים
  python publish.py stage [--repo shiurim-a05]   מעתיק מ-G: + משך (ffprobe)
  python publish.py push  [--repo ...]           commit+push+Pages לכל ריפו
  python publish.py catalog         כותב data.js לקטלוג
  python publish.py all             הכל ברצף
  python publish.py status
  python publish.py verify          בודק כל קובץ באתר מול G: ומעלה מחדש קבצים קטועים
"""
import argparse, json, os, shutil, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

SRC_ROOT = r"G:\האחסון שלי\שיעורי תורה ופרשת שבוע\ואהבת"
BASE = r"C:\shiurim-audio"
MEDIA = os.path.join(BASE, "media")
SITE = "veahavta"
CATALOG_DIR = os.path.join(BASE, SITE)
MANIFEST = os.path.join(CATALOG_DIR, "tools", "manifest.json")
LOG = os.path.join(BASE, "publish-veahavta.log")
OWNER = "yudataub"
PREFIX = "veahavta-a"
PACK_BYTES = 900 * 1000 * 1000
MAX_FILE = 95 * 1024 * 1024
COMMIT_BYTES = 250 * 1000 * 1000      # push בכמה commits — push ענק נכשל יותר
AUDIO_EXT = {"mp3", "m4a"}
EXCLUDE_TOPICS = ()   # אודיו בלבד — וידאו לא בשלב הזה


def log(*a):
    line = time.strftime("[%Y-%m-%d %H:%M:%S] ") + " ".join(str(x) for x in a)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load():
    if os.path.exists(MANIFEST):
        with open(MANIFEST, encoding="utf-8") as f:
            return json.load(f)
    return {"files": [], "repos": {}}


def save(m):
    tmp = MANIFEST + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=0)
    os.replace(tmp, MANIFEST)


def topic_num(rel):
    t = rel.split("\\")[0]
    return t.split(" ")[0] if t[:2].isdigit() else "xx"


# ---------- plan ----------
def plan(m):
    known = {f["rel"] for f in m["files"]}
    new = []
    for d, dirs, fs in os.walk(SRC_ROOT):
        dirs.sort()
        for n in sorted(fs):
            ext = n.rsplit(".", 1)[-1].lower()
            if ext not in AUDIO_EXT:
                continue
            p = os.path.join(d, n)
            rel = os.path.relpath(p, SRC_ROOT)
            if rel.split("\\")[0].startswith(EXCLUDE_TOPICS) or rel in known:
                continue
            new.append({"rel": rel, "size": os.path.getsize(p), "ext": ext})
    # "קבצים כוללים..." אחרונים — כך עותק במקום ה"אמיתי" שלו הוא זה שעולה
    new.sort(key=lambda x: (x["rel"].startswith("קבצים כוללים"), x["rel"]))
    seen = {(os.path.basename(f["rel"]), f["size"]): f["id"] for f in m["files"] if not f.get("dup_of")}
    next_id = max([f["id"] for f in m["files"]], default=0) + 1
    # ממשיכים למלא את הריפו האחרון, ואז פותחים חדש
    used = {}
    for f in m["files"]:
        if f.get("repo"):
            used[f["repo"]] = used.get(f["repo"], 0) + f["size"]
    cur = max(used, default=None)
    if cur and m["repos"].get(cur, {}).get("cleaned"):
        cur = None   # הריפו האחרון כבר נמחק מקומית — קבצים חדשים פותחים ריפו חדש
    for f in new:
        f["id"] = next_id; next_id += 1
        key = (os.path.basename(f["rel"]), f["size"])
        if key in seen:   # אותו קובץ בתיקייה אחרת — לא מעלים פעמיים
            f["repo"] = None; f["skip"] = "כפול"; f["dup_of"] = seen[key]
            m["files"].append(f); continue
        seen[key] = f["id"]
        if f["size"] == 0:
            f["repo"] = None; f["skip"] = "ריק"
        elif f["size"] > MAX_FILE:
            f["repo"] = None; f["skip"] = "גדול מ-95MB"
        else:
            if cur is None or used[cur] + f["size"] > PACK_BYTES:
                n = 1
                while "%s%02d" % (PREFIX, n) in used or "%s%02d" % (PREFIX, n) in m["repos"]:
                    n += 1
                cur = "%s%02d" % (PREFIX, n); used[cur] = 0
            used[cur] += f["size"]
            f["repo"] = cur
            f["path"] = "a/%d.%s" % (f["id"], f["ext"])
        m["files"].append(f)
    for r in used:
        m["repos"].setdefault(r, {"created": False, "pages": False})
    save(m)
    log("plan: %d חדשים, %d ריפואים, %d מדולגים (גדולים)" %
        (len(new), len(used), sum(1 for f in new if f.get("skip"))))


# ---------- stage ----------
def probe(p):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=nw=1:nk=1", p], capture_output=True, text=True, timeout=120)
        return round(float(out.stdout.strip()))
    except Exception:
        return 0


def stage_one(f):
    dst = os.path.join(MEDIA, f["repo"], f["path"].replace("/", "\\"))
    if not (os.path.exists(dst) and os.path.getsize(dst) == f["size"]):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        # כונן G: (Drive for Desktop) מחזיר לפעמים קובץ חלקי בלי שגיאה — 4 קבצים עלו
        # קטועים כך ב-2026-10-06. לכן בודקים גודל אחרי ההעתקה ומנסים שוב.
        for attempt in range(5):
            shutil.copyfile(os.path.join(SRC_ROOT, f["rel"]), dst + ".part")
            if os.path.getsize(dst + ".part") == f["size"]:
                break
            log("  העתקה חלקית (%d/%d בייט) — מנסה שוב: %s" % (os.path.getsize(dst + ".part"), f["size"], f["rel"]))
            time.sleep(10)
        else:
            raise RuntimeError("העתקה חלקית שוב ושוב: %s" % f["rel"])
        os.replace(dst + ".part", dst)
    if not f.get("dur"):
        f["dur"] = probe(dst)
    if not f["dur"]:
        # ffprobe לא מצליח לקרוא = גם הדפדפן לא ינגן. בפועל: קובץ ריק, ו-686 מקטעי
        # סטרימינג בני ~4.6 שניות בלי כותרת אתחול (02\פסיכולוגיה חיובית\קבצים ממוספרים)
        f["skip"] = "פגום - לא ניתן לנגן"
    f["staged"] = True
    return f


def stage(m, repo=None):
    todo = [f for f in m["files"] if f.get("repo") and not f.get("staged") and (not repo or f["repo"] == repo)]
    log("stage: %d קבצים להעתקה" % len(todo))
    done = 0
    with ThreadPoolExecutor(4) as ex:
        for f in ex.map(stage_one, todo):
            done += 1
            if done % 25 == 0:
                save(m); log("  הועתקו %d/%d" % (done, len(todo)))
    save(m)


# ---------- push ----------
def git(cwd, *args, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode:
        raise RuntimeError("git %s: %s" % (" ".join(args), r.stderr.strip()[-500:]))
    return r.stdout


def gh(*args, check=True):
    r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode:
        raise RuntimeError("gh %s: %s" % (" ".join(args), r.stderr.strip()[-500:]))
    return r


def push_repo(m, repo):
    files = [f for f in m["files"] if f.get("repo") == repo]
    if m["repos"][repo].get("cleaned"):
        return   # כבר עלה במלואו והעותק המקומי נמחק
    if not files or not all(f.get("staged") for f in files):
        log("push %s: לא כל הקבצים הועתקו — מדלג" % repo); return
    d = os.path.join(MEDIA, repo)
    st = m["repos"][repo]
    if not os.path.isdir(os.path.join(d, ".git")):
        git(d, "init", "-b", "main")
    git(d, "config", "user.name", "yuda")
    git(d, "config", "user.email", "%s@users.noreply.github.com" % OWNER)
    if not os.path.exists(os.path.join(d, ".nojekyll")):
        with open(os.path.join(d, ".nojekyll"), "w"): pass
        with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as fh:
            fh.write('<meta charset="utf-8"><meta http-equiv="refresh" content="0;url=https://%s.github.io/%s/">' % (OWNER, SITE))
    if not st.get("created"):
        if gh("repo", "view", "%s/%s" % (OWNER, repo), check=False).returncode:
            # GitHub מגביל קצב יצירת ריפואים ("too many repositories, too quickly") — ממתינים ומנסים שוב
            for attempt in range(30):
                r = gh("repo", "create", "%s/%s" % (OWNER, repo), "--public",
                       "--description", "קבצי אודיו לספריית ואהבת - https://%s.github.io/%s/" % (OWNER, SITE), check=False)
                if r.returncode == 0:
                    break
                if "too quickly" not in r.stderr:
                    raise RuntimeError("gh repo create %s: %s" % (repo, r.stderr.strip()[-300:]))
                log("  מגבלת קצב של GitHub על יצירת ריפואים — ממתין 10 דקות (%d)" % (attempt + 1))
                time.sleep(600)
            else:
                raise RuntimeError("gh repo create %s: מגבלת קצב לא השתחררה" % repo)
        if "origin" not in git(d, "remote"):
            git(d, "remote", "add", "origin", "https://github.com/%s/%s.git" % (OWNER, repo))
        st["created"] = True; save(m)
    # commits בגדלים של עד COMMIT_BYTES, push אחרי כל אחד
    git(d, "add", ".nojekyll", "index.html")
    pending = [f for f in files if not f.get("pushed")]
    batch, size = [], 0
    def flush():
        nonlocal batch, size
        if not batch and git(d, "status", "--porcelain") == "":
            return
        git(d, "add", "--", *[f["path"] for f in batch])
        if git(d, "diff", "--cached", "--name-only").strip():
            git(d, "commit", "-q", "-m", "audio %d files" % len(batch))
        for attempt in range(4):
            r = subprocess.run(["git", "push", "-u", "origin", "main"], cwd=d, capture_output=True, text=True)
            if r.returncode == 0: break
            log("  push נכשל (%d): %s" % (attempt + 1, r.stderr.strip()[-200:])); time.sleep(30)
        else:
            raise RuntimeError("push %s נכשל" % repo)
        for f in batch: f["pushed"] = True
        save(m); log("  %s: נדחפו %d קבצים (%.0fMB)" % (repo, len(batch), size / 1e6))
        batch, size = [], 0
    for f in pending:
        batch.append(f); size += f["size"]
        if size >= COMMIT_BYTES: flush()
    flush()
    if not st.get("pages"):
        r = gh("api", "-X", "POST", "repos/%s/%s/pages" % (OWNER, repo),
               "-f", "source[branch]=main", "-f", "source[path]=/", check=False)
        if r.returncode and "already" not in (r.stderr + r.stdout).lower():
            log("  Pages %s: %s" % (repo, r.stderr.strip()[-200:]))
        else:
            st["pages"] = True; save(m)
    log("push %s: הושלם" % repo)
    # העותק המקומי כבר לא נחוץ — הכל ב-GitHub. מוחקים כדי לא לתפוס 30GB ב-C:
    if st.get("pages"):
        shutil.rmtree(d, onerror=lambda fn, p, e: (os.chmod(p, 0o666), fn(p)))
        st["cleaned"] = True; save(m); log("  %s: העותק המקומי נמחק" % repo)


# ---------- catalog ----------
def drop_near_dups(items, weak=("misc", "other", "compil")):
    """אותו שם + אותו אורך (±3%) = אותו שיעור שהועתק לכמה תיקיות. משאירים אחד:
    בנושא ספציפי (לא "שונות"/רצפים) ובקובץ הגדול. ב-2026-10-06 זה הוריד 646 כפילויות
    מקטלוג השיעורים ו-96 מואהבת — הקבצים נשארים ב-GitHub, רק לא מוצגים פעמיים."""
    import re
    def norm(t):
        return re.sub(r"\s*\(\d+\)\s*$", "", t).strip()
    rank = lambda x: (x["c"] in weak, -x["z"])
    keep, seen = [], {}
    for x in sorted(items, key=rank):
        k = norm(x["t"])
        if x["d"] and any(abs(x["d"] - d) <= max(5, 0.03 * d) for d in seen.get(k, ())):
            continue
        seen.setdefault(k, []).append(x["d"])
        keep.append(x)
    keep.sort(key=lambda x: x["i"])
    return keep


def catalog(m):
    import collections
    import topics as T
    items = []
    for f in m["files"]:
        if not f.get("pushed") or f.get("skip"):
            continue
        name = os.path.basename(f["rel"])
        items.append({
            "i": f["id"],
            "t": T.clean_title(name),
            "c": T.classify(name),
            "s": "",
            "u": "https://%s.github.io/%s/%s" % (OWNER, f["repo"], f["path"]),
            "d": f.get("dur", 0),
            "z": f["size"],
        })
    # סדרה = תחילית כותרת שחוזרת לפחות 3 פעמים באותו נושא
    cnt = collections.Counter((x["c"], T.series_key(x["t"])) for x in items)
    for x in items:
        k = T.series_key(x["t"])
        tname = next((t[2] for t in T.TOPICS if t[0] == x["c"]), "")
        if k and cnt[(x["c"], k)] >= 3 and k not in tname:   # "נעמה הנגבי" בתוך נושא נעמה — לא סדרה
            x["s"] = k
    before = len(items)
    items = drop_near_dups(items)
    if before != len(items):
        log("catalog: %d כפילויות הוסתרו" % (before - len(items)))
    used = {x["c"] for x in items}
    meta = [dict(id=t[0], e=t[1], n=t[2], d=t[3], a=t[4], g=t[5]) for t in T.TOPICS if t[0] in used]
    out = os.path.join(CATALOG_DIR, "data.js")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("// נוצר ע\"י tools/publish.py catalog - אל תערכו ידנית\nwindow.TOPICS=")
        json.dump(meta, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write(";\nwindow.LESSONS=")
        json.dump(items, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write(";\nwindow.LESSONS_UPDATED=%s;\n" % json.dumps(time.strftime("%d/%m/%Y")))
    log("catalog: %d שיעורים ב-data.js" % len(items))
    publish_catalog(len(items))


def publish_catalog(n):
    """commit+push לריפו הקטלוג — כך האתר מתעדכן אחרי כל ריפו מדיה שעלה."""
    d = CATALOG_DIR
    if not os.path.isdir(os.path.join(d, ".git")):
        return
    git(d, "add", "index.html", "data.js", "README.md", ".nojekyll", ".gitignore",
        "tools/publish.py", "tools/topics.py", "tools/old_catalog_map.json",
        "tools/manifest.json", "HANDOFF.md")
    if not git(d, "diff", "--cached", "--name-only").strip():
        return
    git(d, "commit", "-q", "-m", "catalog: %d lessons" % n)
    r = subprocess.run(["git", "push", "-u", "origin", "main"], cwd=d, capture_output=True, text=True)
    if r.returncode:
        log("  push קטלוג נכשל: %s" % r.stderr.strip()[-200:]); return
    if not os.path.exists(os.path.join(d, "tools", ".pages")):
        r = gh("api", "-X", "POST", "repos/%s/%s/pages" % (OWNER, SITE),
               "-f", "source[branch]=main", "-f", "source[path]=/", check=False)
        if r.returncode == 0 or "already" in (r.stderr + r.stdout).lower():
            open(os.path.join(d, "tools", ".pages"), "w").close()
    log("  הקטלוג פורסם (%d שיעורים)" % n)


# ---------- verify ----------
def verify(m, fix=True):
    """HEAD לכל קובץ שעלה; גודל שגוי (העתקה קטועה מ-G:) → העלאה מחדש דרך ה-Contents API."""
    import base64, tempfile, urllib.request
    files = [f for f in m["files"] if f.get("pushed") and not f.get("skip")]

    def head(f):
        url = "https://%s.github.io/%s/%s" % (OWNER, f["repo"], f["path"])
        for _ in range(3):
            try:
                r = urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30)
                return int(r.headers.get("Content-Length", -1))
            except Exception:
                time.sleep(2)
        return -1
    with ThreadPoolExecutor(8) as ex:
        sizes = list(ex.map(head, files))
    bad = [f for f, z in zip(files, sizes) if z != f["size"]]
    log("verify: %d קבצים, %d בגודל שגוי" % (len(files), len(bad)))
    if not fix:
        return bad
    for f in bad:
        src = os.path.join(SRC_ROOT, f["rel"])
        for attempt in range(5):
            data = open(src, "rb").read()
            if len(data) == f["size"]:
                break
            time.sleep(10)
        else:
            log("  לא הצלחתי לקרוא קובץ שלם: %s" % f["rel"]); continue
        api = "repos/%s/%s/contents/%s" % (OWNER, f["repo"], f["path"])
        sha = gh("api", api, "--jq", ".sha").stdout.strip()
        body = {"message": "fix truncated %s" % f["path"], "content": base64.b64encode(data).decode(),
                "sha": sha, "committer": {"name": "yuda", "email": "%s@users.noreply.github.com" % OWNER}}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            json.dump(body, tf); tmp = tf.name
        try:
            r = gh("api", "-X", "PUT", api, "--input", tmp, check=False)
        finally:
            os.remove(tmp)
        if r.returncode:
            log("  תיקון נכשל %s: %s" % (f["path"], r.stderr.strip()[-200:])); continue
        f["dur"] = probe(src) or f.get("dur", 0)
        save(m); log("  תוקן: %s/%s (%s)" % (f["repo"], f["path"], f["rel"]))
    return bad


def status(m):
    fs = m["files"]
    print("קבצים:", len(fs), "| הועתקו:", sum(1 for f in fs if f.get("staged")),
          "| נדחפו:", sum(1 for f in fs if f.get("pushed")), "| מדולגים:", sum(1 for f in fs if f.get("skip")))
    print("ריפואים:", len(m["repos"]), "| עם Pages:", sum(1 for r in m["repos"].values() if r.get("pages")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["plan", "stage", "push", "catalog", "all", "status", "verify"])
    ap.add_argument("--repo")
    a = ap.parse_args()
    m = load()
    repos = [a.repo] if a.repo else sorted(m["repos"])
    if a.cmd in ("plan", "all"): plan(m); repos = [a.repo] if a.repo else sorted(m["repos"])
    if a.cmd == "stage": stage(m, a.repo)
    if a.cmd == "push":
        for r in repos: push_repo(m, r)
    if a.cmd == "all":
        for r in repos:   # ריפו אחרי ריפו — כך הקטלוג מתמלא בהדרגה גם אם עוצרים באמצע
            stage(m, r); push_repo(m, r); catalog(m)
    if a.cmd == "catalog": catalog(m)
    if a.cmd == "status": status(m)
    if a.cmd == "verify":
        if verify(m): catalog(m)


if __name__ == "__main__":
    main()
