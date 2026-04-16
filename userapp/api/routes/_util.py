from sqlalchemy.ext.asyncio import AsyncSession

from userapp.api.util import create_one_endpoint
from userapp.core.models.tables import UserSubmit, User
from userapp.core.schemas.user_submit import UserSubmitTableSchema, UserSubmitPost


async def _patch_user_submit_nodes(session: AsyncSession, user: User, new_submit_nodes: list[UserSubmitPost]):
    """Updates the passed in user to match the provided list of submit_nodes"""

    # Delete the submit nodes that are not in the list of new submit nodes
    for existing_submit_node in user.submit_nodes:
        if existing_submit_node.submit_node_id not in [sn.submit_node_id for sn in new_submit_nodes]:
            delete_stmt = (
                UserSubmit.__table__.delete()
                .where(UserSubmit.user_id == user.id)
                .where(UserSubmit.submit_node_id == existing_submit_node.submit_node_id)
            )
            await session.execute(delete_stmt)

    # Add the missing submit nodes
    for submit_node in new_submit_nodes:

        if submit_node.submit_node_id in [sn.submit_node_id for sn in user.submit_nodes]:
            continue  # Already exists

        # Create nodes for both auth_netid True and False to simplify logic
        for for_auth_netid in [True, False]:
            user_submit_model = UserSubmitTableSchema(
                user_id=user.id,
                for_auth_netid=for_auth_netid,
                **submit_node.model_dump(),
            )
            await create_one_endpoint(session, UserSubmit, user_submit_model)