Installation
============

Depends on libgdal, rasterio, fiona, shapely and numpy.

Using ``uv`` (recommended)::

    uv add rasterstats

Or with pip::

    pip install rasterstats

Platform-specific GDAL setup
-----------------------------

**Ubuntu**::

    sudo apt-get install libgdal-dev gdal-bin

then install rasterstats as above.

**macOS** (Homebrew)::

    brew install gdal

then install rasterstats as above.

**Windows**: follow the `rasterio installation <https://github.com/mapbox/rasterio#windows-1>`_,
then install rasterstats as above.

Tests
-----

To run the python unit tests

    uv run pytest
