from enum import Enum

class RoleEnum(Enum):
    MEMBER = "MEMBER"
    PI = "PI"

class PositionEnum(Enum):
    SELECT = "SELECT"
    FACULTY = "FACULTY"
    STAFF = "STAFF"
    POSTDOC = "POSTDOC"
    GRAD_STUDENT = "GRAD_STUDENT"
    UNDERGRADUATE = "UNDERGRADUATE"
    OTHER = "OTHER"

class HttpRequestMethodEnum(Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"

class FormTypeEnum(Enum):
    USER = "USER"
    PROJECT = "PROJECT"

class FormStatusEnum(Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"

class EntityManagerEnum(Enum):
    """Enum to record what is managing a given entity"""
    APPLICATION = "APPLICATION" # Default - Userapp manual management
    MANIFEST = "MANIFEST" # Manifest Groups
    MORGRIDGE_AD = "MORGRIDGE_ACTIVE_DIRECTORY"

class GroupTypeEnum(Enum):
    SUBMIT_NODE = "SUBMIT_NODE"

# I decided against using this so I could set the values in just the UI
# Keeping it here just incase
class DepartmentEnum(Enum):
    ACCESSIBLE_EDUCATION_MATERIALS = 'Accessible Education Materials'
    AFRICAN_CULTURAL_STUDIES = 'African Cultural Studies'
    AGRICULTURAL_AND_APPLIED_ECONOMICS = 'Agricultural & Applied Economics'
    ALZHEIMERS_DISEASE_RESEARCH_CENTER = "Alzheimer's Disease Research Center"
    ANESTHESIOLOGY = 'Anesthesiology'
    ANIMAL_AND_DAIRY_SCIENCES = 'Animal and Dairy Sciences'
    ANTHROPOLOGY = 'Anthropology'
    AQUATIC_SCIENCES_CENTER = 'Aquatic Sciences Center'
    ASTRONOMY = 'Astronomy'
    ATMOSPHERIC_AND_OCEANIC_SCIENCES = 'Atmospheric & Oceanic Sciences'
    BACTERIOLOGY = 'Bacteriology'
    BIOCHEMISTRY = 'Biochemistry'
    BIOLOGICAL_MAGNETIC_RESONANCE_BANK = 'Biological Magnetic Resonance Bank'
    BIOLOGICAL_SYSTEMS_ENGINEERING = 'Biological Systems Engineering'
    BIOLOGY = 'Biology'
    BIOMEDICAL_ENGINEERING = 'Biomedical Engineering'
    BIOMOLECULAR_CHEMISTRY = 'Biomolecular Chemistry'
    BIOPHYSICS = 'Biophysics'
    BIOSTATISTICS_AND_MEDICAL_INFORMATICS = 'Biostatistics & Medical Informatics'
    BOTANY = 'Botany'
    BUSINESS = 'Business'
    CARBONE_CANCER_CENTER = 'Carbone Cancer Center'
    CELL_AND_REGENERATIVE_BIOLOGY = 'Cell & Regenerative Biology'
    CENTER_FOR_EAST_ASIAN_STUDIES = 'Center for East Asian Studies'
    CENTER_FOR_HEALTHY_MINDS = 'Center for Healthy Minds'
    CHEMICAL_AND_BIOLOGICAL_ENGINEERING = 'Chemical & Biological Engineering'
    CHEMISTRY = 'Chemistry'
    CHTC = 'CHTC'
    CIVIL_AND_ENVIRONMENTAL_ENGINEERING = 'Civil & Environmental Engineering'
    COMMUNICATION_ARTS = 'Communication Arts'
    COMMUNICATION_SCIENCES_AND_DISORDERS = 'Communication Sciences & Disorders'
    COMMUNITY_AND_ENVIRONMENTAL_SOCIOLOGY = 'Community & Environmental Sociology'
    COMPARATIVE_BIOSCIENCES = 'Comparative Biosciences'
    COMPUTER_SCIENCES = 'Computer Sciences'
    CURRICULUM_INSTRUCTION = 'Curriculum Instruction'
    DATA_SCIENCE = 'Data Science'
    DOIT = 'DoIT'
    ECONOMICS = 'Economics'
    EDUCATIONAL_LEADERSHIP = 'Educational Leadership'
    EDUCATIONAL_POLICY_STUDIES = 'Educational Policy Studies'
    EDUCATIONAL_PSYCHOLOGY = 'Educational Psychology'
    ELECTRICAL_AND_COMPUTER_ENGINEERING = 'Electrical & Computer Engineering'
    ENGINE_RESEARCH_CENTER = 'Engine Research Center'
    ENGINEERING_PHYSICS = 'Engineering Physics'
    ENTOMOLOGY = 'Entomology'
    FINANCE = 'Finance'
    FOOD_SCIENCE = 'Food Science'
    FORESTRY_AND_WILDLIFE_ECOLOGY = 'Forestry & Wildlife Ecology'
    GENETICS = 'Genetics'
    GEOGRAPHY = 'Geography'
    GEOSCIENCE = 'Geoscience'
    HISTORY = 'History'
    HUMAN_ONCOLOGY = 'Human Oncology'
    INDUSTRIAL_AND_SYSTEMS_ENGINEERING = 'Industrial & Systems Engineering'
    INFLUENZA_RESEARCH_INSTITUTE = 'Influenza Research Institute'
    INFORMATION_SCHOOL = 'Information School'
    INTEGRATIVE_BIOLOGY = 'Integrative Biology'
    JOURNALISM = 'Journalism'
    KINESIOLOGY = 'Kinesiology'
    LAW = 'Law'
    LIBRARY = 'Library'
    LIFE_SCIENCES_COMMUNICATION = 'Life Sciences Communication'
    LIMNOLOGY = 'Limnology'
    MANAGEMENT_AND_HUMAN_RESOURCES = 'Management & Human Resources'
    MARKETING = 'Marketing'
    MATERIALS_SCIENCE_AND_ENGINEERING = 'Materials Science & Engineering'
    MATH = 'Math'
    MECHANICAL_ENGINEERING = 'Mechanical Engineering'
    MEDICAL_ENGINEERING = 'Medical Engineering'
    MEDICAL_MICROBIOLOGY_AND_IMMUNOLOGY = 'Medical Microbiology & Immunology'
    MEDICAL_PHYSICS = 'Medical Physics'
    MEDICINE = 'Medicine'
    MOLECULAR_VIROLOGY = 'Molecular Virology'
    MORGRIDGE_INSTITUTE_FOR_RESEARCH = 'Morgridge Institute for Research'
    NELSON_INSTITUTE_FOR_ENVIRONMENTAL_STUDIES = 'Nelson Institute for Environmental Studies'
    NEUROLOGICAL_SURGERY = 'Neurological Surgery'
    NEUROLOGY = 'Neurology'
    NEUROSCIENCE = 'Neuroscience'
    NUCLEAR_ENGINEERING = 'Nuclear Engineering'
    NUTRITIONAL_SCIENCES = 'Nutritional Sciences'
    OBSTETRICS_AND_GYNECOLOGY = 'Obstetrics & Gynecology'
    OCEANOGRAPHY = 'Oceanography'
    OFF_CAMPUS = 'Off-Campus'
    OPERATIONS_AND_INFORMATION_MANAGEMENT = 'Operations and Information Management'
    OPTHALMOLOGY = 'Opthalmology'
    ORTHOPEDICS = 'Orthopedics'
    OSG = 'OSG'
    PATHOLOGY = 'Pathology'
    PEDIATRICS = 'Pediatrics'
    PHARMACEUTICAL_SCIENCES = 'Pharmaceutical Sciences'
    PHARMACY = 'Pharmacy'
    PHYSICS = 'Physics'
    PLANT_AND_AGROECOSYSTEM_SCIENCES = 'Plant and Agroecosystem Sciences'
    PLANT_PATHOLOGY = 'Plant Pathology'
    POLITICAL_SCIENCE = 'Political Science'
    POPULATION_HEALTH_SCIENCE = 'Population Health Science'
    PSYCHIATRY = 'Psychiatry'
    PSYCHOLOGY = 'Psychology'
    PUBLIC_AFFAIRS = 'Public Affairs'
    RADIOLOGY = 'Radiology'
    REAL_ESTATE = 'Real Estate'
    RISK_AND_INSURANCE = 'Risk and Insurance'
    SOIL_SCIENCE = 'Soil Science'
    SPANISH_AND_PORTUGUESE = 'Spanish and Portuguese'
    SSEC = 'SSEC'
    STATISTICS = 'Statistics'
    SURGERY = 'Surgery'
    SURGICAL_SCIENCES = 'Surgical Sciences'
    TRAFFIC_OPERATIONS_AND_SAFETY_LABORATORY = 'Traffic Operations & Safety Laboratory'
    UNIVERSITIES_OF_WISCONSIN = 'Universities of Wisconsin'
    UROLOGY = 'Urology'
    VIROLOGY = 'Virology'
    WAISMAN = 'Waisman'
    WCER = 'WCER'
    WEI = 'WEI'
    WID = 'WID'
    OTHER = 'Other'
