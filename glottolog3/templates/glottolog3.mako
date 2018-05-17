<%inherit file="app.mako"/>
<%! active_menu_item = None %>
<%block name="brand">
  <a class="brand" href="${request.route_url('dataset')}" title="${request.dataset.name}">
      <img src="${request.static_url('glottolog3:static/glottolog_logo.png')}" width="28"/>
      Glottolog
  </a>
</%block>
${next.body()}
