# -*- coding: utf-8 -*-
#
# scikit-learn documentation build configuration file, created by
# sphinx-quickstart on Fri Jan  8 09:13:42 2010.
#
# This file is execfile()d with the current directory set to its containing
# dir.
#
# Note that not all possible configuration values are present in this
# autogenerated file.
#
# All configuration values have a default; values that are commented out
# serve to show the default.

import sys
import os
import warnings
import re
from packaging.version import parse
from pathlib import Path

# If extensions (or modules to document with autodoc) are in another
# directory, add these directories to sys.path here. If the directory
# is relative to the documentation root, use os.path.abspath to make it
# absolute, like shown here.
sys.path.insert(0, os.path.abspath('sphinxext'))

from github_link import make_linkcode_resolve
import sphinx_gallery

# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom ones.
extensions = [
    'sphinx.ext.autodoc', 'sphinx.ext.autosummary',
    'numpydoc',
    'sphinx.ext.linkcode', 'sphinx.ext.doctest',
    'sphinx.ext.intersphinx',
    'sphinx.ext.imgconverter',
    'sphinx_gallery.gen_gallery',
    'sphinx_issues'
]

# this is needed for some reason...
# see https://github.com/numpy/numpydoc/issues/69
numpydoc_class_members_toctree = False


# For maths, use mathjax by default and svg if NO_MATHJAX env variable is set
# (useful for viewing the doc offline)
if os.environ.get('NO_MATHJAX'):
    extensions.append('sphinx.ext.imgmath')
    imgmath_image_format = 'svg'
    mathjax_path = ''
else:
    extensions.append('sphinx.ext.mathjax')
    mathjax_path = 'file:///usr/share/javascript/mathjax/MathJax.js?config=TeX-AMS_CHTML'

autodoc_default_options = {
    'members': True,
    'inherited-members': True
}

# Add any paths that contain templates here, relative to this directory.
templates_path = ['templates']

# generate autosummary even if no references
autosummary_generate = True

# The suffix of source filenames.
source_suffix = '.rst'

# The encoding of source files.
#source_encoding = 'utf-8'

# The master toctree document.
master_doc = 'contents'

# General information about the project.
project = 'scikit-learn'
copyright = '2007 - 2020, scikit-learn developers (BSD License)'

# The version info for the project you're documenting, acts as replacement for
# |version| and |release|, also used in various other places throughout the
# built documents.
#
# The short X.Y version.
import sklearn
parsed_version = parse(sklearn.__version__)
version = ".".join(parsed_version.base_version.split(".")[:2])
# The full version, including alpha/beta/rc tags.
# Removes post from release name
if parsed_version.is_postrelease:
    release = parsed_version.base_version
else:
    release = sklearn.__version__

# The language for content autogenerated by Sphinx. Refer to documentation
# for a list of supported languages.
#language = None

# There are two options for replacing |today|: either, you set today to some
# non-false value, then it is used:
#today = ''
# Else, today_fmt is used as the format for a strftime call.
#today_fmt = '%B %d, %Y'

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
exclude_patterns = ['_build', 'templates', 'includes', 'themes']

# The reST default role (used for this markup: `text`) to use for all
# documents.
default_role = 'literal'

# If true, '()' will be appended to :func: etc. cross-reference text.
add_function_parentheses = False

# If true, the current module name will be prepended to all description
# unit titles (such as .. function::).
#add_module_names = True

# If true, sectionauthor and moduleauthor directives will be shown in the
# output. They are ignored by default.
#show_authors = False

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = 'sphinx'

# A list of ignored prefixes for module index sorting.
#modindex_common_prefix = []


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  Major themes that come with
# Sphinx are currently 'default' and 'sphinxdoc'.
html_theme = 'scikit-learn-modern'

# Theme options are theme-specific and customize the look and feel of a theme
# further.  For a list of options available for each theme, see the
# documentation.
html_theme_options = {'google_analytics': False,
                      'mathjax_path': mathjax_path}

# Add any paths that contain custom themes here, relative to this directory.
html_theme_path = ['themes']


# The name for this set of Sphinx documents.  If None, it defaults to
# "<project> v<release> documentation".
#html_title = None

# A shorter title for the navigation bar.  Default is the same as html_title.
html_short_title = 'scikit-learn'

# The name of an image file (relative to this directory) to place at the top
# of the sidebar.
html_logo = 'logos/scikit-learn-logo-small.png'

# The name of an image file (within the static path) to use as favicon of the
# docs.  This file should be a Windows icon file (.ico) being 16x16 or 32x32
# pixels large.
html_favicon = 'logos/favicon.ico'

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['images']

# If not '', a 'Last updated on:' timestamp is inserted at every page bottom,
# using the given strftime format.
#html_last_updated_fmt = '%b %d, %Y'

# Custom sidebar templates, maps document names to template names.
#html_sidebars = {}

# Additional templates that should be rendered to pages, maps page names to
# template names.
html_additional_pages = {
    'index': 'index.html',
    'documentation': 'documentation.html'}  # redirects to index

# If false, no module index is generated.
html_domain_indices = False

# If false, no index is generated.
html_use_index = False

# If true, the index is split into individual pages for each letter.
#html_split_index = False

# If true, links to the reST sources are added to the pages.
#html_show_sourcelink = True

# If true, an OpenSearch description file will be output, and all pages will
# contain a <link> tag referring to it.  The value of this option must be the
# base URL from which the finished HTML is served.
#html_use_opensearch = ''

# If nonempty, this is the file name suffix for HTML files (e.g. ".xhtml").
#html_file_suffix = ''

# Output file base name for HTML help builder.
htmlhelp_basename = 'scikit-learndoc'

# If true, the reST sources are included in the HTML build as _sources/name.
html_copy_source = True

# Adds variables into templates
html_context = {}
# finds latest release highlights and places it into HTML context for
# index.html
release_highlights_dir = Path("..") / "examples" / "release_highlights"
# Finds the highlight with the latest version number
latest_highlights = sorted(release_highlights_dir.glob(
                           "plot_release_highlights_*.py"))[-1]
latest_highlights = latest_highlights.with_suffix('').name
html_context["release_highlights"] = \
    f"auto_examples/release_highlights/{latest_highlights}"

# get version from higlight name assuming highlights have the form
# plot_release_highlights_0_22_0
highlight_version = ".".join(latest_highlights.split("_")[-3:-1])
html_context["release_highlights_version"] = highlight_version

# -- Options for LaTeX output ------------------------------------------------
latex_elements = {
    # The paper size ('letterpaper' or 'a4paper').
    # 'papersize': 'letterpaper',

    # The font size ('10pt', '11pt' or '12pt').
    # 'pointsize': '10pt',

    # Additional stuff for the LaTeX preamble.
    'preamble': r"""
        \usepackage{amsmath}\usepackage{amsfonts}\usepackage{bm}
        \usepackage{morefloats}\usepackage{enumitem} \setlistdepth{10}
        """
}

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title, author, documentclass
# [howto/manual]).
latex_documents = [('contents', 'user_guide.tex', 'scikit-learn user guide',
                    'scikit-learn developers', 'manual'), ]

# The name of an image file (relative to this directory) to place at the top of
# the title page.
latex_logo = "logos/scikit-learn-logo.png"

# Documents to append as an appendix to all manuals.
# latex_appendices = []

# If false, no module index is generated.
latex_domain_indices = False

trim_doctests_flags = True

# intersphinx configuration
intersphinx_mapping = {
    'python': ('https://docs.python.org/{.major}'.format(
         sys.version_info), '/usr/share/doc/python3/html/objects.inv'),
    'numpy': ('https://docs.scipy.org/doc/numpy/', '/usr/share/doc/python-numpy-doc/html/objects.inv'),
    'scipy': ('https://docs.scipy.org/doc/scipy/reference', '/usr/share/doc/python-scipy-doc/html/objects.inv'),
    'matplotlib': ('https://matplotlib.org/', '/usr/share/doc/python-matplotlib-doc/html/objects.inv'),
    'pandas': ('https://matplotlib.org/', '/usr/share/doc/python-pandas-doc/html/objects.inv'),
}

v = parse(release)
if v.release is None:
    raise ValueError(
        'Ill-formed version: {!r}. Version should follow '
        'PEP440'.format(version))

if v.is_devrelease:
    binder_branch = 'master'
else:
    major, minor = v.release[:2]
    binder_branch = '{}.{}.X'.format(major, minor)


class SubSectionTitleOrder:
    """Sort example gallery by title of subsection.

    Assumes README.txt exists for all subsections and uses the subsection with
    dashes, '---', as the adornment.
    """
    def __init__(self, src_dir):
        self.src_dir = src_dir
        self.regex = re.compile(r"^([\w ]+)\n-", re.MULTILINE)

    def __repr__(self):
        return '<%s>' % (self.__class__.__name__,)

    def __call__(self, directory):
        src_path = os.path.normpath(os.path.join(self.src_dir, directory))

        # Forces Release Highlights to the top
        if os.path.basename(src_path) == "release_highlights":
            return "0"

        readme = os.path.join(src_path, "README.txt")

        try:
            with open(readme, 'r') as f:
                content = f.read()
        except FileNotFoundError:
            return directory

        title_match = self.regex.search(content)
        if title_match is not None:
            return title_match.group(1)
        return directory


sphinx_gallery_conf = {
    'doc_module': 'sklearn',
    'backreferences_dir': os.path.join('modules', 'generated'),
    'show_memory': False,
    'reference_url': {
        'sklearn': None},
    'examples_dirs': ['../examples'],
    'gallery_dirs': ['auto_examples'],
    'subsection_order': SubSectionTitleOrder('../examples'),
    # avoid generating too many cross links
    'inspect_global_variables': False,
    'remove_config_comments': True,
}


# The following dictionary contains the information used to create the
# thumbnails for the front page of the scikit-learn home page.
# key: first image in set
# values: (number of plot in set, height of thumbnail)
carousel_thumbs = {'sphx_glr_plot_classifier_comparison_001.png': 600}


# enable experimental module so that experimental estimators can be
# discovered properly by sphinx
from sklearn.experimental import enable_hist_gradient_boosting  # noqa
from sklearn.experimental import enable_iterative_imputer  # noqa


def make_carousel_thumbs(app, exception):
    """produces the final resized carousel images"""
    if exception is not None:
        return
    print('Preparing carousel images')

    image_dir = os.path.join(app.builder.outdir, '_images')
    for glr_plot, max_width in carousel_thumbs.items():
        image = os.path.join(image_dir, glr_plot)
        if os.path.exists(image):
            c_thumb = os.path.join(image_dir, glr_plot[:-4] + '_carousel.png')
            sphinx_gallery.gen_rst.scale_image(image, c_thumb, max_width, 190)


def filter_search_index(app, exception):
    if exception is not None:
        return

    # searchindex only exist when generating html
    if app.builder.name != 'html':
        return

    print('Removing methods from search index')

    searchindex_path = os.path.join(app.builder.outdir, 'searchindex.js')
    with open(searchindex_path, 'r') as f:
        searchindex_text = f.read()

    searchindex_text = re.sub(r'{__init__.+?}', '{}', searchindex_text)
    searchindex_text = re.sub(r'{__call__.+?}', '{}', searchindex_text)

    with open(searchindex_path, 'w') as f:
        f.write(searchindex_text)


# Config for sphinx_issues

# we use the issues path for PRs since the issues URL will forward
issues_github_path = 'scikit-learn/scikit-learn'


def setup(app):
    # to hide/show the prompt in code examples:
    app.connect('build-finished', make_carousel_thumbs)
    app.connect('build-finished', filter_search_index)


# The following is used by sphinx.ext.linkcode to provide links to github
linkcode_resolve = make_linkcode_resolve('sklearn',
                                         'https://github.com/scikit-learn/'
                                         'scikit-learn/blob/{revision}/'
                                         '{package}/{path}#L{lineno}')

warnings.filterwarnings("ignore", category=UserWarning,
                        message='Matplotlib is currently using agg, which is a'
                                ' non-GUI backend, so cannot show the figure.')
