"""Initial database schema for AccessPPT.

Revision ID: 001_initial
Revises:
Create Date: 2026-10-06 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('is_superuser', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    # 2. presentations
    op.create_table(
        'presentations',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('filename', sa.String(length=500), nullable=False),
        sa.Column('original_filename', sa.String(length=500), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('slide_count', sa.Integer(), nullable=True),
        sa.Column('object_count', sa.Integer(), nullable=True),
        sa.Column('original_s3_key', sa.String(length=1000), nullable=True),
        sa.Column('processed_s3_key', sa.String(length=1000), nullable=True),
        sa.Column('report_s3_key', sa.String(length=1000), nullable=True),
        sa.Column('accessibility_score', sa.Float(), nullable=True),
        sa.Column('error_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('warning_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('review_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('pass_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='uploaded'),
        sa.Column('celery_task_id', sa.String(length=255), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('pptx_width_emu', sa.Integer(), nullable=True),
        sa.Column('pptx_height_emu', sa.Integer(), nullable=True),
        sa.Column('presentation_language', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_presentations_user_id', 'presentations', ['user_id'])

    # 3. slides
    op.create_table(
        'slides',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('presentation_id', sa.String(length=36), sa.ForeignKey('presentations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('slide_index', sa.Integer(), nullable=False),
        sa.Column('slide_number', sa.Integer(), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('title_placeholder_id', sa.String(length=50), nullable=True),
        sa.Column('speaker_notes', sa.Text(), nullable=True),
        sa.Column('has_notes', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('accessibility_score', sa.Float(), nullable=True),
        sa.Column('error_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('warning_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('slide_xml_hash', sa.String(length=64), nullable=True),
        sa.Column('thumbnail_s3_key', sa.String(length=1000), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_slides_presentation_id', 'slides', ['presentation_id'])

    # 4. slide_objects
    op.create_table(
        'slide_objects',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('slide_id', sa.String(length=36), sa.ForeignKey('slides.id', ondelete='CASCADE'), nullable=False),
        sa.Column('presentation_id', sa.String(length=36), sa.ForeignKey('presentations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('shape_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=500), nullable=True),
        sa.Column('object_type', sa.String(length=50), nullable=False),
        sa.Column('left_emu', sa.Integer(), nullable=True),
        sa.Column('top_emu', sa.Integer(), nullable=True),
        sa.Column('width_emu', sa.Integer(), nullable=True),
        sa.Column('height_emu', sa.Integer(), nullable=True),
        sa.Column('text_content', sa.Text(), nullable=True),
        sa.Column('alt_text', sa.Text(), nullable=True),
        sa.Column('alt_text_title', sa.String(length=500), nullable=True),
        sa.Column('is_decorative', sa.Boolean(), nullable=True),
        sa.Column('reading_order', sa.Integer(), nullable=True),
        sa.Column('has_audio', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('has_video', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('has_animation', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('chart_title', sa.String(length=500), nullable=True),
        sa.Column('has_table_headers', sa.Boolean(), nullable=True),
        sa.Column('image_hash', sa.String(length=128), nullable=True),
        sa.Column('image_s3_key', sa.String(length=1000), nullable=True),
        sa.Column('ai_analyzed', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('ai_suggestions', sa.JSON(), nullable=True),
        sa.Column('extra_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_slide_objects_slide_id', 'slide_objects', ['slide_id'])
    op.create_index('ix_slide_objects_presentation_id', 'slide_objects', ['presentation_id'])

    # 5. accessibility_issues
    op.create_table(
        'accessibility_issues',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('presentation_id', sa.String(length=36), sa.ForeignKey('presentations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('slide_id', sa.String(length=36), sa.ForeignKey('slides.id', ondelete='CASCADE'), nullable=True),
        sa.Column('object_id', sa.String(length=36), sa.ForeignKey('slide_objects.id', ondelete='CASCADE'), nullable=True),
        sa.Column('rule_id', sa.String(length=50), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('why_it_matters', sa.Text(), nullable=True),
        sa.Column('recommendation', sa.Text(), nullable=True),
        sa.Column('standard_reference', sa.String(length=200), nullable=True),
        sa.Column('context_data', sa.JSON(), nullable=True),
        sa.Column('auto_fix_supported', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('manual_review_required', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='open'),
        sa.Column('ai_analyzed', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('ai_suggestion', sa.Text(), nullable=True),
        sa.Column('ai_confidence', sa.Float(), nullable=True),
        sa.Column('ai_confidence_level', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fixed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_accessibility_issues_presentation_id', 'accessibility_issues', ['presentation_id'])
    op.create_index('ix_accessibility_issues_slide_id', 'accessibility_issues', ['slide_id'])
    op.create_index('ix_accessibility_issues_object_id', 'accessibility_issues', ['object_id'])
    op.create_index('ix_accessibility_issues_rule_id', 'accessibility_issues', ['rule_id'])
    op.create_index('ix_accessibility_issues_category', 'accessibility_issues', ['category'])
    op.create_index('ix_accessibility_issues_severity', 'accessibility_issues', ['severity'])

    # 6. ai_suggestions
    op.create_table(
        'ai_suggestions',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('presentation_id', sa.String(length=36), sa.ForeignKey('presentations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('object_id', sa.String(length=36), sa.ForeignKey('slide_objects.id', ondelete='CASCADE'), nullable=True),
        sa.Column('check_type', sa.String(length=100), nullable=False),
        sa.Column('result', sa.String(length=100), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('confidence_level', sa.String(length=20), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('suggestion', sa.Text(), nullable=True),
        sa.Column('raw_response', sa.JSON(), nullable=True),
        sa.Column('is_valid', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('human_review_recommended', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_ai_suggestions_presentation_id', 'ai_suggestions', ['presentation_id'])
    op.create_index('ix_ai_suggestions_object_id', 'ai_suggestions', ['object_id'])

    # 7. remediation_actions
    op.create_table(
        'remediation_actions',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('issue_id', sa.String(length=36), sa.ForeignKey('accessibility_issues.id', ondelete='CASCADE'), nullable=False),
        sa.Column('presentation_id', sa.String(length=36), sa.ForeignKey('presentations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('action_type', sa.String(length=100), nullable=False),
        sa.Column('action_data', sa.JSON(), nullable=True),
        sa.Column('applied_by', sa.String(length=50), nullable=False, server_default='auto'),
        sa.Column('success', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_remediation_actions_issue_id', 'remediation_actions', ['issue_id'])
    op.create_index('ix_remediation_actions_presentation_id', 'remediation_actions', ['presentation_id'])

    # 8. analysis_runs
    op.create_table(
        'analysis_runs',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('presentation_id', sa.String(length=36), sa.ForeignKey('presentations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('celery_task_id', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('progress', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('current_step', sa.String(length=200), nullable=True),
        sa.Column('steps_completed', sa.JSON(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_analysis_runs_presentation_id', 'analysis_runs', ['presentation_id'])

    # 9. reports
    op.create_table(
        'reports',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('presentation_id', sa.String(length=36), sa.ForeignKey('presentations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('format', sa.String(length=20), nullable=False),
        sa.Column('s3_key', sa.String(length=1000), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_reports_presentation_id', 'reports', ['presentation_id'])

    # 10. verification_results
    op.create_table(
        'verification_results',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('presentation_id', sa.String(length=36), sa.ForeignKey('presentations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('visual_changes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('content_changes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('layout_changes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('accessibility_changes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_verification_results_presentation_id', 'verification_results', ['presentation_id'])


def downgrade() -> None:
    op.drop_table('verification_results')
    op.drop_table('reports')
    op.drop_table('analysis_runs')
    op.drop_table('remediation_actions')
    op.drop_table('ai_suggestions')
    op.drop_table('accessibility_issues')
    op.drop_table('slide_objects')
    op.drop_table('slides')
    op.drop_table('presentations')
    op.drop_table('users')
