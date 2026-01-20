from flask import Blueprint

cases_bp = Blueprint('cases', __name__)

from . import routes
