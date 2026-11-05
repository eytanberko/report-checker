"""Description of the data the reports are based on. Given to the LLM so it can write SQL."""

TABLE = "energy"
DATA_PATH = "data/energy.csv"

SCHEMA = """
Table `energy` (one row per country per year, 2010-2025; source: Our World in Data).
Countries: Israel, Greece, Cyprus, Jordan, Egypt, Spain, Portugal, Italy, Turkey, Morocco,
Germany, Netherlands, Chile, Australia, United Arab Emirates, Saudi Arabia, World.
Some countries have no 2025 row yet (latest = 2024).

Columns:
- country (text), year (int), population (people)
- renewables_share_elec  : % of electricity generated from renewables (0-100)
- solar_share_elec       : % of electricity from solar (0-100)
- wind_share_elec        : % of electricity from wind (0-100)
- gas_share_elec         : % of electricity from natural gas (0-100)
- coal_share_elec        : % of electricity from coal (0-100)
- oil_share_elec         : % of electricity from oil (0-100)
- fossil_share_elec      : % of electricity from all fossil fuels (0-100)
- electricity_generation : total electricity generated, TWh
- per_capita_electricity : electricity generation per person, kWh
- carbon_intensity_elec  : grams of CO2 per kWh of electricity
"""
