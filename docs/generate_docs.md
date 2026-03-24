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

## 3) Важливо для Google-style docstrings

У `docs/source/conf.py` увімкнено:

- `sphinx.ext.napoleon`
- `napoleon_google_docstring = True`
- `napoleon_numpy_docstring = False`

Тобто в проєкті використовується саме Google-style формат секцій (`Args`, `Returns`, `Raises`, тощо).
