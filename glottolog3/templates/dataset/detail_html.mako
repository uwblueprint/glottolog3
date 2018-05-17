<%inherit file="../home_comp.mako"/>
<%namespace name="util" file="../util.mako"/>
<% TxtCitation = h.get_adapter(h.interfaces.IRepresentation, ctx, request, ext='md.txt') %>

<div class="row-fluid">
    <div class="span12">
        <h2>Welcome to Glottolog</h2>
    <p class="lead">
        Comprehensive reference information for the world's languages, especially the
        lesser known languages.
    </p>
    </div>
</div>
