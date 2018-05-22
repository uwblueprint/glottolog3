<%inherit file="../home_comp.mako"/>
<div class="row-fluid">
    <div class="span12">
        <h1>Language Ontology API Guide</h1>

        <h2>Search Endpoint</h2>
        <p><code>/search?q={search query}&multilingual={true or false}&whole={true or false}</code></p>
        <p><b>q:</b> The string to be searched on</p>
        <p><b>multilingual:</b> Whether or not to search all languages, rather than just English (optional, default true)</p>
        <p><b>whole:</b> Whether or not to verbatim search the query string (optional, default false)</p>

        <h2>Languoid Admin Endpoints</h2>
        <h4>GET</h4>
        <p><code>/languoid/{id}</code>, e.g. <code>/languoid/stan1293</code></p>
        <h4>POST</h4>
        <p>To add a languoid, create a POST request to <code>/languoid</code> with sample payload below:</p>
        <pre><code>
        {
          "id": "test0000", # this is the alphanumeric code (glottocode, probably)
          "name": "Test",
          "level": "dialect",
          "status": "safe"
        }
        </code></pre>
        <p>There are also longitude, latitude, hid, bookkeeping and newick fields.
        To add a descendant, create a POST request to <code>/languoid/{glottocode}/descendant</code> with sample payload:</p>
        <pre><code>
        {
          "descendant": "test0000"
        }
        </code></pre>
        <p>To add a child, create a POST request to <code>/languoid/{glottocode}/child</code> with sample payload:</p>
        <pre><code>
        {
          "child": "test0000"
        }
        </code></pre>
        <h4>PUT</h4>
        <p>To change a languoid, create a PUT request to <code>/languoid/{id}</code> with sample payload:</p>
        <pre><code>
        {
          // Any subset of the fields above that need to be updated, for example:
          "name": "Test",
          "latitude": 0,
          "longitude": 0
        }
        </code></pre>
        <h4>DELETE</h4>
        <p>To delete a languoid, simply create a DELETE request to <code>/languoid/{id}</code>.
        This renders the languoid inactive and thus will not show up in search queries or requests.</p>

        <h2>Identifier Admin Endpoints</h2>
        <h4>GET</h4>
        <p>request to <code>/identifier/{type}/{name}</code> ie. <code>/identifier/name/Test_011</code></p>
        <h4>POST</h4>
        <p>To add an identifier, create a POST request to <code>/identifier/{type}/{name}</code> with sample payload below:</p>
        <pre><code>
        {
          "lang": "en",
          "name": "Test_011",
          "type": "name",
          "description": "lexvo"
        }
        </code></pre>
        <p>This will return a JSON object with the added identifier on success and an error message on failure.</p>
        <h4>PUT</h4>
        <p>To update an existing identifier, make a PUTrequest to <code>/identifiers/{type}/{name}</code>, takes a JSON body with the following fields (an example below):</p>
        <pre><code>
        {
          // Any subset of the fields above that need to be updated, for example:
          "lang": "fr",
          "description": "new"
        }
        </code></pre>
        <p>This will return a JSON object of the updated identifier and an error message otherwise.</p>
        <h4>DELETE</h4>
        <p>create a DELETE request to <code>/identifiers/{type}/{name}</code>. Will return an empty JSON object if success and message if failed.</p>
    </div>
</div>
