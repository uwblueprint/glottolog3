from functools import partial

import os
from pyramid.httpexceptions import HTTPGone, HTTPMovedPermanently
from pyramid.config import Configurator
from pyramid.events import NewRequest
from pyramid.response import Response
from sqlalchemy.orm import joinedload, joinedload_all
from clld.interfaces import ICtxFactoryQuery, IDownload
from clld.web.app import menu_item, CtxFactoryQuery
from clld.web.adapters.base import adapter_factory, Index
from clld.web.adapters.download import N3Dump, Download
from clld.web.adapters.cldf import CldfDownload
from clld.db.models.common import Language, Source, ValueSet, ValueSetReference

import glottolog3
from glottolog3 import views
from glottolog3 import models
from glottolog3 import adapters
from glottolog3.config import CFG
from glottolog3.interfaces import IProvider
from glottolog3.datatables import Providers


class GLCtxFactoryQuery(CtxFactoryQuery):
    def refined_query(self, query, model, req):
        if model == Language:
            query = query.options(
                joinedload(models.Languoid.family),
                joinedload(models.Languoid.children),
                joinedload_all(
                    Language.valuesets, ValueSet.references, ValueSetReference.source)
            )
        return query

    def __call__(self, model, req):
        if model == Language:
            # responses for no longer supported legacy codes
            if not models.Languoid.get(req.matchdict['id'], default=None):
                legacy = models.LegacyCode.get(req.matchdict['id'], default=None)
                if legacy:
                    raise HTTPMovedPermanently(location=legacy.url(req))
            #
            # FIXME: how to serve HTTP 410 for legacy codes?
            #
        elif model == Source:
            if ':' in req.matchdict['id']:
                ref = req.db.query(models.Source)\
                    .join(models.Refprovider)\
                    .filter(models.Refprovider.id == req.matchdict['id'])\
                    .first()
                if ref:
                    raise HTTPMovedPermanently(location=req.route_url('source', id=ref.id))
        return super(GLCtxFactoryQuery, self).__call__(model, req)

def add_cors_headers_response_callback(event):
    # TODO whitelist which sites are allowed Access-Control-Allow-Origin
    def cors_headers(request, response):
        response.headers.update({
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST,GET,DELETE,PUT,OPTIONS',
        'Access-Control-Allow-Headers': 'Origin, Content-Type, Accept, Authorization',
        'Access-Control-Allow-Credentials': 'true',
        'Access-Control-Max-Age': '1728000',
        })
    event.request.add_response_callback(cors_headers)

def main(global_config, **settings):
    """ This function returns a Pyramid WSGI application.
    """
    settings.update(CFG)
    db_url = os.environ.get('GLOTTOLOG_DATABASE_URL')
    if db_url is not None:
        settings['sqlalchemy.url'] = db_url
    settings['navbar.inverse'] = True
    settings['route_patterns'] = {
        'languages': '/glottolog/language',
        'language': '/resource/languoid/id/{id:[^/\.]+}',
        'source': '/resource/reference/id/{id:[^/\.]+}',
        'sources': '/langdoc',
        #'provider': '/langdoc/langdocinformation#provider-{id}',
        'providers': '/langdoc/langdocinformation',
    }
    settings['sitemaps'] = ['language', 'source']
    config = Configurator(settings=settings)

    config.include('clldmpg')
    config.add_route_and_view(
        'robots',
        '/robots.txt',
        lambda req: Response(
            'Sitemap: {0}\nUser-agent: *\nDisallow: /files/\n'.format(
                req.route_url('sitemapindex')),
            content_type='text/plain'))
    config.registry.registerUtility(GLCtxFactoryQuery(), ICtxFactoryQuery)
    config.register_menu()

    # Endpoints created by UW Blueprint
    config.add_route(
        'glottolog.search',
        '/search')
    config.add_route(
        'glottolog.get_identifier',
        '/identifier/{type}/{name}',
        request_method='GET')
    config.add_route(
        'glottolog.add_identifier',
        'languoid/{glottocode}/identifier',
        request_method='POST')
    config.add_route(
        'glottolog.put_identifier',
        '/identifier/{type}/{name}',
        request_method='PUT')
    config.add_route(
        'glottolog.delete_identifier',
        '/identifier/{type}/{name}',
        request_method='DELETE')
    config.add_route(
        'glottolog.get_languoid',
        '/languoid/{glottocode}',
        request_method='GET')
    config.add_route(
        'glottolog.add_languoid',
        '/languoid',
        request_method='POST')
    config.add_route(
        'glottolog.put_languoid',
        '/languoid/{glottocode}',
        request_method='PUT')
    config.add_route(
        'glottolog.delete_languoid',
        '/languoid/{glottocode}',
        request_method='DELETE')
    config.add_route(
        'glottolog.add_descendant',
        '/languoid/{glottocode}/descendant',
        request_method='POST')
    config.add_route(
        'glottolog.add_child',
        '/languoid/{glottocode}/child',
        request_method='POST')

    # UW blueprint code ends here

    config.add_subscriber(add_cors_headers_response_callback, NewRequest)
    return config.make_wsgi_app()
