"""
Data Ingestion Flow using Prefect and dlt
This demonstrates the "Glue" integration between Prefect and dlt
"""

import asyncio
from datetime import datetime
from typing import Dict, Any, List
import pandas as pd

from prefect import flow, task, get_run_logger
from dlt import pipeline, sources
from dlt.destinations import postgres

from src.core.config import settings


@task
def extract_data(data_source: str) -> List[Dict[str, Any]]:
    """
    Extract data from source (simulated).
    In production, this would connect to various data sources.
    """
    logger = get_run_logger()
    logger.info(f"Extracting data from {data_source}")

    # Simulate data extraction
    sample_data = [
        {
            "id": 1,
            "name": "John Doe",
            "email": "john@example.com",
            "phone": "555-1234",
            "tenant_id": "tenant_001",
            "created_at": datetime.utcnow().isoformat()
        },
        {
            "id": 2,
            "name": "Jane Smith",
            "email": "jane@example.com",
            "phone": "555-5678",
            "tenant_id": "tenant_001",
            "created_at": datetime.utcnow().isoformat()
        },
        {
            "id": 3,
            "name": "Bob Johnson",
            "email": "bob@example.com",
            "phone": "555-9876",
            "tenant_id": "tenant_002",
            "created_at": datetime.utcnow().isoformat()
        }
    ]

    logger.info(f"Extracted {len(sample_data)} records")
    return sample_data


@task
def apply_pii_redaction(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Apply PII redaction using Microsoft Presidio.
    """
    logger = get_run_logger()
    logger.info("Applying PII redaction")

    try:
        # Try to import Presidio
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine

        analyzer = AnalyzerEngine()
        anonymizer = AnonymizerEngine()

        redacted_data = []
        for record in data:
            # Analyze and anonymize PII
            text_fields = ["name", "email", "phone"]
            redacted_record = record.copy()

            for field in text_fields:
                if field in record:
                    # Analyze the text
                    results = analyzer.analyze(
                        text=record[field],
                        language="en"
                    )

                    # Anonymize if PII detected
                    if results:
                        anonymized = anonymizer.anonymize(
                            text=record[field],
                            analyzer_results=results
                        )
                        redacted_record[field] = anonymized.text

            redacted_data.append(redacted_record)

        logger.info(f"PII redaction applied to {len(redacted_data)} records")
        return redacted_data

    except ImportError:
        logger.warning("Presidio not installed, skipping PII redaction")
        return data


@task
def apply_ai_labeling(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Apply AI labeling using OpenAI API.
    """
    logger = get_run_logger()
    logger.info("Applying AI labeling")

    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.OPENAI_API_KEY)

        labeled_data = []
        for record in data:
            # Create labeling prompt
            prompt = f"""
            Analyze this record and assign labels:
            Name: {record.get('name', 'N/A')}
            Email: {record.get('email', 'N/A')}
            Phone: {record.get('phone', 'N/A')}

            Assign one of these categories:
            - 'high_value' (appears to be enterprise/corporate)
            - 'medium_value' (appears to be small business)
            - 'low_value' (appears to be personal)

            Also provide a confidence score (0-1).

            Return JSON: {{"category": "...", "confidence": ..., "reasoning": "..."}}
            """

            # Call OpenAI API (synchronous)
            response = client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a data labeling expert."},
                    {"role": "user", "content": prompt}
                ],
                temperature=settings.OPENAI_TEMPERATURE,
                max_tokens=200
            )

            # Parse response
            import json
            ai_result = json.loads(response.choices[0].message.content)

            # Add AI results to record
            labeled_record = record.copy()
            labeled_record.update({
                "ai_category": ai_result.get("category"),
                "ai_confidence": ai_result.get("confidence"),
                "ai_reasoning": ai_result.get("reasoning"),
                "ai_model": settings.OPENAI_MODEL,
                "ai_processed_at": datetime.utcnow().isoformat()
            })

            labeled_data.append(labeled_record)

        logger.info(f"AI labeling applied to {len(labeled_data)} records")
        return labeled_data

    except Exception as e:
        logger.error(f"AI labeling failed: {str(e)}")
        # Return data without AI labels
        for record in data:
            record["ai_error"] = str(e)
        return data


@task
def route_for_human_review(data: List[Dict[str, Any]]) -> tuple[List[Dict], List[Dict]]:
    """
    Route records based on confidence scores.
    Low confidence records go to Label Studio.
    """
    logger = get_run_logger()
    logger.info("Routing records for human review")

    auto_approved = []
    human_review = []

    for record in data:
        confidence = record.get("ai_confidence", 1.0)

        if confidence < settings.CONFIDENCE_THRESHOLD:
            human_review.append(record)
            logger.info(f"Record {record['id']} routed for human review (confidence: {confidence})")
        else:
            auto_approved.append(record)
            logger.info(f"Record {record['id']} auto-approved (confidence: {confidence})")

    logger.info(f"Auto-approved: {len(auto_approved)}, Human review: {len(human_review)}")
    return auto_approved, human_review


@task
def send_to_label_studio(data: List[Dict[str, Any]]) -> bool:
    """
    Send low-confidence records to Label Studio for human review.
    """
    logger = get_run_logger()
    logger.info(f"Sending {len(data)} records to Label Studio")

    try:
        from label_studio_sdk import Client

        # Connect to Label Studio
        ls = Client(
            url=settings.LABEL_STUDIO_URL,
            api_key=settings.LABEL_STUDIO_API_KEY
        )

        # Get or create project
        project = ls.get_project(settings.LABEL_STUDIO_PROJECT_ID)

        # Create tasks for human review
        tasks = []
        for record in data:
            task_data = {
                "data": {
                    "record_id": record["id"],
                    "original_data": record,
                    "ai_category": record.get("ai_category"),
                    "ai_confidence": record.get("ai_confidence"),
                    "ai_reasoning": record.get("ai_reasoning")
                }
            }
            tasks.append(task_data)

        # Import tasks
        if tasks:
            project.import_tasks(tasks)
            logger.info(f"Successfully imported {len(tasks)} tasks to Label Studio")

        return True

    except Exception as e:
        logger.error(f"Failed to send to Label Studio: {str(e)}")
        return False


@task
def save_to_database(data: List[Dict[str, Any]], table_name: str = "processed_data") -> bool:
    """
    Save processed data to PostgreSQL using dlt.
    """
    logger = get_run_logger()
    logger.info(f"Saving {len(data)} records to {table_name}")

    try:
        # Create dlt pipeline
        pipeline_obj = pipeline(
            pipeline_name="data_foundry_ingestion",
            destination=postgres(settings.DATABASE_URL_SYNC),
            dataset_name="public"
        )

        # Create a simple source
        def data_source():
            for record in data:
                yield record

        # Run pipeline
        load_info = pipeline_obj.run(data_source(), table_name=table_name)

        logger.info(f"Successfully saved {len(data)} records to database")
        logger.info(f"Load info: {load_info}")
        return True

    except Exception as e:
        logger.error(f"Failed to save to database: {str(e)}")
        return False


@flow(name="Data Foundry Ingestion Flow")
async def data_ingestion_flow(
    data_source: str = "sample_data",
    enable_ai_labeling: bool = True,
    enable_pii_redaction: bool = True,
    enable_human_review: bool = True
):
    """
    Main ingestion flow that orchestrates the entire data processing pipeline.

    Args:
        data_source: Source of data to process
        enable_ai_labeling: Whether to apply AI labeling
        enable_pii_redaction: Whether to apply PII redaction
        enable_human_review: Whether to route low confidence for human review
    """
    logger = get_run_logger()
    logger.info("Starting Data Foundry Ingestion Flow")

    try:
        # Step 1: Extract data
        raw_data = await extract_data(data_source)

        # Step 2: Apply PII redaction
        if enable_pii_redaction:
            redacted_data = await apply_pii_redaction(raw_data)
        else:
            redacted_data = raw_data

        # Step 3: Apply AI labeling
        if enable_ai_labeling and settings.OPENAI_API_KEY:
            labeled_data = await apply_ai_labeling(redacted_data)
        else:
            labeled_data = redacted_data
            logger.info("Skipping AI labeling")

        # Step 4: Route for human review
        if enable_human_review:
            auto_approved, human_review = await route_for_human_review(labeled_data)
        else:
            auto_approved = labeled_data
            human_review = []

        # Step 5: Send low confidence to Label Studio
        if human_review and settings.LABEL_STUDIO_API_KEY:
            await send_to_label_studio(human_review)

        # Step 6: Save auto-approved data to database
        if auto_approved:
            await save_to_database(auto_approved, "auto_approved_data")

        # Step 7: Save human review queue to database
        if human_review:
            await save_to_database(human_review, "human_review_queue")

        logger.info("Data Ingestion Flow completed successfully")
        return {
            "total_records": len(raw_data),
            "auto_approved": len(auto_approved),
            "human_review": len(human_review),
            "success": True
        }

    except Exception as e:
        logger.error(f"Data Ingestion Flow failed: {str(e)}")
        raise


if __name__ == "__main__":
    # Run the flow locally for testing
    asyncio.run(
        data_ingestion_flow(
            data_source="sample_data",
            enable_ai_labeling=False,  # Disable AI for testing without API keys
            enable_pii_redaction=False,  # Disable PII for testing
            enable_human_review=False
        )
    )