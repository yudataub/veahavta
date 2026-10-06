# המשך עבודה — ספריית ואהבת

עודכן: 2026-10-06

- **האתר:** https://yudataub.github.io/veahavta/ — ריפו `yudataub/veahavta`, מקומי `C:\shiurim-audio\veahavta`
- **מקור:** `G:\האחסון שלי\שיעורי תורה ופרשת שבוע\ואהבת` (Drive for Desktop)
- **מדיה:** `yudataub/veahavta-a01` … `a35`, עד 900MB כל אחד, GitHub Pages
- **בסיס החלוקה:** הקטלוג הישן `מסמכים\שונות\קטלוגים\📚 ספריית ואהבת.html` → `tools/old_catalog_map.json`
- **אח תאום:** קטלוג השיעורים `C:\shiurim-audio\shiurim` (אותו כלי, אותו נגן) — ראו ה-HANDOFF שם למלכודות

## מה נכנס
1,655 קבצי אודיו ייחודיים. 311 כפולים (אותו שם+גודל) לא עלו; 7 מעל 95MB לא עלו; וידאו — לא.

## לשנות חלוקה לנושאים — בלי להעלות מחדש
`tools/topics.py`: `TOPICS` (שם/אימוג'י/תיאור/צבע/קבוצה בעמוד הבית: speaker / theme / long),
`SPEAKERS`/`THEMES` (מילות מפתח), וסדר העדיפויות: `part_NNN_` → רצפים; הקטלוג הישן; מילות מפתח.
אחרי שינוי: `python -X utf8 tools/publish.py catalog`.

## פקודות
```
cd C:\shiurim-audio\veahavta\tools
python -X utf8 publish.py status
python -X utf8 publish.py all      # קבצים חדשים / המשך אחרי הפסקה
python -X utf8 publish.py catalog
```

## פתוח
- "שונות" עדיין 131 קבצים — לעבור עליהם עם המשתמש
- כפילויות "כמעט" (אותו שם, גודל שונה) עדיין מופיעות פעמיים
