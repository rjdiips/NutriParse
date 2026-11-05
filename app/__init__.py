"""NutriParse application package.

The package is split by responsibility:

- ``config``      runtime paths, limits, and ``.env`` loading
- ``journal``     the shared JSON journal store and its validation rules
- ``services``    LLM, nutrition, recipe, and image generation logic
- ``web``         FastAPI app, HTTP dependencies, and routers
- ``cli``         the interactive terminal front end
"""

__version__ = "1.0.0"
