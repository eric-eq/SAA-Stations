# Seismological Association of Australia StationXml files

This repository contains individual StationXML files for the SubSurface Observatory stations in Sydney and surrounding areas. Each station has its own XML file (e.g., DU.ALEX.xml, DU.USYD.xml, etc.).

Combined StationXML

For convenience, all individual station files are automatically merged into a single file called all.xml. This is done using ObsPy, ensuring the result is a valid StationXML file.

How it works:

* GitHub Action (.github/workflows/combine-xml.yml) runs on every push to main that modifies one or more .xml station files.
* The workflow:
	1.	Installs Python and ObsPy
	2.	Reads all station XML files (excluding all.xml)
	3.	Merges them into a single Inventory
	4.	Writes the result to all.xml
	5.	Commits and pushes the updated all.xml back to the repository

Triggering the workflow
* Edit or add any *.xml file (other than all.xml) and push the change to main.
* The workflow will run automatically and update all.xml.

You can monitor the workflow runs under the Actions tab in GitHub.
