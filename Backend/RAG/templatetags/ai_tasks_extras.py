"""
Template filters for AI Tasks result rendering.

render_citations reuses citation_service.render_answer_html() verbatim
- the exact same escape-then-linkify-[n]-markers logic Ask AI's result
panel already uses - so AI Task result text (summary, per-dimension
findings, report section bodies, ...) gets the same safe, clickable
citation treatment without a second implementation of the escaping/
substitution logic.
"""

from django import template

from ..services.citation_service import render_answer_html

register = template.Library()


@register.filter(name="render_citations")
def render_citations(text):
    return render_answer_html(text)
