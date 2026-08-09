import rdflib

g = rdflib.Graph()
print("Parsing full schema.org RDF (this may take a moment)...")
g.parse("schemas/schemaorg.rdf", format="xml")

# The classes in the hierarchy for Course
classes = [
    rdflib.URIRef("https://schema.org/Course"),
    rdflib.URIRef("https://schema.org/CreativeWork"),
    rdflib.URIRef("https://schema.org/Thing")
]

# We also want HTTP variants since schema.org sometimes mixes them in the RDF
http_classes = [rdflib.URIRef(str(c).replace("https", "http")) for c in classes]
all_target_classes = classes + http_classes

print(f"Target classes: {all_target_classes}")

out_g = rdflib.Graph()
# Bind prefixes
out_g.bind("schema", "http://schema.org/")
out_g.bind("rdfs", "http://www.w3.org/2000/01/rdf-schema#")

# Add the Course class definition
course_ref = rdflib.URIRef("https://schema.org/Course")
for p, o in g.predicate_objects(course_ref):
    out_g.add((course_ref, p, o))

# Find all properties whose domainIncludes matches one of our target classes
SCHEMA = rdflib.Namespace("https://schema.org/")
SCHEMA_HTTP = rdflib.Namespace("http://schema.org/")

prop_count = 0
for s, p, o in g.triples((None, rdflib.RDF.type, rdflib.RDF.Property)):
    # Check if domainIncludes matches our target
    domain_includes = list(g.objects(s, SCHEMA.domainIncludes)) + list(g.objects(s, SCHEMA_HTTP.domainIncludes))
    
    if any(d in all_target_classes for d in domain_includes):
        # We want this property!
        # Re-map its domain to just Course so our loader doesn't have to understand inheritance
        out_g.add((s, rdflib.RDF.type, rdflib.RDF.Property))
        out_g.add((s, SCHEMA_HTTP.domainIncludes, rdflib.URIRef("http://schema.org/Course")))
        
        # Keep its range and label/comment
        for r in g.objects(s, SCHEMA.rangeIncludes):
            out_g.add((s, SCHEMA_HTTP.rangeIncludes, r))
        for r in g.objects(s, SCHEMA_HTTP.rangeIncludes):
            out_g.add((s, SCHEMA_HTTP.rangeIncludes, r))
            
        for l in g.objects(s, rdflib.RDFS.label):
            out_g.add((s, rdflib.RDFS.label, l))
        for c in g.objects(s, rdflib.RDFS.comment):
            out_g.add((s, rdflib.RDFS.comment, c))
            
        prop_count += 1

print(f"Found {prop_count} properties for Course hierarchy.")
out_g.serialize("schemas/course_schema.rdf", format="xml")
print("Saved to schemas/course_schema.rdf")
