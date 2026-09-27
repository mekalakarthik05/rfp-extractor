from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict

class RFPData(BaseModel):
    """
    The exact schema of 20 fields required by the assignment.
    Null vs 'Not Specified' is handled via Optional type allowing None.
    """
    model_config = ConfigDict(extra='forbid', protected_namespaces=())

    bid_number: Optional[str] = Field(
        default=None, 
        description="The unique identifier for the bid or RFP. Do not guess; extract exactly as written."
    )
    title: Optional[str] = Field(
        default=None, 
        description="The title or name of the bid/RFP project."
    )
    due_date: Optional[str] = Field(
        default=None, 
        description="The proposal or bid submission deadline date and time. Do not confuse with pre-bid meeting date or delivery date. Preserve timezone if present."
    )
    bid_submission_type: Optional[str] = Field(
        default=None, 
        description="How the bid must be submitted (e.g., e-procurement portal, sealed hard copy, email). Include portal name/URL if mentioned."
    )
    term_of_bid: Optional[str] = Field(
        default=None, 
        description="Contract duration, performance period, renewal options, and total duration limits (e.g., '1 year', '36 months', '3-year agreement with two 1-year renewals, max 5 years'). Do not confuse with delivery dates or proposal validity periods. Null if not specified."
    )
    pre_bid_meeting: Optional[str] = Field(
        default=None, 
        description="Date, time, location, and/or virtual meeting details (platform, URL, Meeting ID, Passcode) of the pre-bid meeting. Note if it is mandatory. Do not confuse with bid due date."
    )
    installation: Optional[str] = Field(
        default=None, 
        description=(
            "Installation, deployment, setup, or configuration requirements explicitly described in the source. "
            "This includes: physical device installation, software installation, device deployment and setup, "
            "asset tagging/etching/decaling, configuration services, imaging, specialized deployment or delivery services, "
            "and any related on-site service requirements. "
            "Extract verbatim or closely paraphrased from the source. "
            "Do NOT infer installation from the mere fact that goods are being delivered. "
            "Only populate when the source explicitly describes such requirements or services. "
            "Null if not mentioned."
        )
    )
    bid_bond_requirement: Optional[str] = Field(
        default=None, 
        description="Capture percentage or flat amount for bid bond, or explicit 'not required'. Do not convert amounts or assume 5%."
    )
    delivery_date: Optional[str] = Field(
        default=None, 
        description="When goods/services are expected to arrive, delivery timeframe, or anticipated delivery start timing. Do not confuse with contract term. Null if absent."
    )
    payment_terms: Optional[str] = Field(
        default=None, 
        description="Payment terms (e.g., 'Net 30'). Null if absent."
    )
    additional_documentation_required: Optional[List[str]] = Field(
        default=None, 
        description="List of required forms/certificates (e.g., W-9, references, non-collusion affidavit). One item per form. Do not invent standard forms."
    )
    mfg_for_registration: Optional[str] = Field(
        default=None, 
        description="Required manufacturer for partner registration (only where the bidder must be a registered/authorised partner). A brand merely mentioned as 'or equal' is not this field."
    )
    contract_or_cooperative_to_use: Optional[str] = Field(
        default=None, 
        description="Sourcewell, OMNIA, NASPO, GSA, state contract vehicles, etc. Null if none named."
    )
    model_no: Optional[str] = Field(
        default=None, 
        description=(
            "Verbatim model number(s) required by the RFP. Exact casing and punctuation. Never construct or guess. "
            "When the procurement contains multiple products or models, include ALL relevant model identifiers "
            "joined by ', ' (e.g., 'ModelA, ModelB'). Do not discard a model identifier simply because another was found first."
        )
    )
    part_no: Optional[str] = Field(
        default=None, 
        description="Verbatim part numbers. Exact casing and punctuation. Never construct or guess."

    )
    product: Optional[str] = Field(
        default=None, 
        description="The primary product or category of goods/services requested."
    )
    contact_info: Optional[str] = Field(
        default=None, 
        description="Purchasing/procurement contact name, email, and phone. Prefer the one designated for bid questions. Do not merge multiple people."
    )
    company_name: Optional[str] = Field(
        default=None, 
        description="Issuing agency, school district, or municipality. Not the consultant, not the incumbent vendor."
    )
    bid_summary: Optional[str] = Field(
        default=None, 
        description="2-3 sentences summarising the bid, strictly grounded in the document. No marketing language."
    )
    product_specification: Optional[str] = Field(
        default=None, 
        description="Condensed technical criteria (dimensions, capacities, standards). Do not fabricate specs. If only a general scope is present, summarise it from the text."
    )
