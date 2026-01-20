from flask import Blueprint

display_bp = Blueprint('display', __name__)

from . import routes
