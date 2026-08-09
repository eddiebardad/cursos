import rdflib

g = rdflib.Graph()
g.parse("schemas/course_schema.rdf", format="xml")

SCHEMA_HTTP = rdflib.Namespace("http://schema.org/")
DCTERMS = rdflib.Namespace("http://purl.org/dc/terms/")
Course = rdflib.URIRef("http://schema.org/Course")

# Add price
price_ref = rdflib.URIRef("http://schema.org/price")
g.add((price_ref, rdflib.RDF.type, rdflib.RDF.Property))
g.add((price_ref, SCHEMA_HTTP.domainIncludes, Course))
g.add((price_ref, SCHEMA_HTTP.rangeIncludes, SCHEMA_HTTP.Float))
g.add((price_ref, SCHEMA_HTTP.rangeIncludes, SCHEMA_HTTP.Text))

# Add priceCurrency
price_currency_ref = rdflib.URIRef("http://schema.org/priceCurrency")
g.add((price_currency_ref, rdflib.RDF.type, rdflib.RDF.Property))
g.add((price_currency_ref, SCHEMA_HTTP.domainIncludes, Course))
g.add((price_currency_ref, SCHEMA_HTTP.rangeIncludes, SCHEMA_HTTP.Text))

# Add offers_url (Custom flat property)
offers_url_ref = rdflib.URIRef("http://schema.org/offers_url")
g.add((offers_url_ref, rdflib.RDF.type, rdflib.RDF.Property))
g.add((offers_url_ref, SCHEMA_HTTP.domainIncludes, Course))
g.add((offers_url_ref, SCHEMA_HTTP.rangeIncludes, SCHEMA_HTTP.URL))

# Add dcterms:identifier
identifier_ref = rdflib.URIRef("http://purl.org/dc/terms/identifier")
g.add((identifier_ref, rdflib.RDF.type, rdflib.RDF.Property))
g.add((identifier_ref, SCHEMA_HTTP.domainIncludes, Course))
g.add((identifier_ref, SCHEMA_HTTP.rangeIncludes, SCHEMA_HTTP.Text))

g.serialize("schemas/course_schema.rdf", format="xml")
print("Injected flat properties (price, priceCurrency, offers_url, dcterms:identifier) into course_schema.rdf")
