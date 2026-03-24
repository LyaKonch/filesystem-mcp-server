# Генерація документації

Цей файл дублює базові кроки зі сторінки `docs/source/usage.rst`.

## 1) Збірка HTML-документації

Із кореня проєкту (Windows):

```powershell
.\make.bat html
```

Після успішної збірки документація буде згенерована в `docs/build/html`.

## 2) Корисні команди

Показати доступні таргети Sphinx:

```powershell
.\make.bat help
```

Очистити артефакти збірки:

```powershell
.\make.bat clean
```

## 3) Двомовна документація (EN + UA)

Важливо: Sphinx **не перекладає автоматично** зміст документації без перекладів.
Українська версія формується через `gettext` + переклади у `.po`:

- шаблони: `docs/build/gettext/*.pot`
- переклади: `docs/source/locale/uk/LC_MESSAGES/*.po`

Локальна збірка двох мов:

```powershell
python -m sphinx -b gettext docs/source docs/build/gettext
python -m sphinx -b html docs/source docs/build/html
python -m sphinx -b html -D language=uk docs/source docs/build/html/uk
```

Результат:
- English: `docs/build/html/index.html`
- Українська: `docs/build/html/uk/index.html`

## 4) CI/CD публікація

Workflow: `.github/workflows/docs-publish.yml`

Він робить таке:
1. на GitHub Actions запускає збірку EN та UA;
2. формує артефакти у `docs/build/html` на раннері;
3. публікує результат у гілку `gh-pages`.

Тобто:
- в робочих гілках (`main`, `docs/code-documentation`) лежать **джерела**;
- у `gh-pages` лежить **згенерований сайт**.

## 5) Важливо для Google-style docstrings

У `docs/source/conf.py` увімкнено:

- `sphinx.ext.napoleon`
- `napoleon_google_docstring = True`
- `napoleon_numpy_docstring = False`

Тобто в проєкті використовується саме Google-style формат секцій (`Args`, `Returns`, `Raises`, тощо).
