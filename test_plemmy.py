import json
from plemmy.lemmyhttp import LemmyHttp

# Initialize the Lemmy client with the base URL
lemmy = LemmyHttp(base_url="https://lemdro.id")

# Authenticate with your Lemmy account
response = lemmy.login(username_or_email="???????", password="****")
post_id = 14923936 

# Check login response
if response.status_code == 200:
    print("Logged in successfully!")
    community_info = lemmy.get_community(name="materialdesign")

    if community_info.status_code == 200:
        print("Community Info retrieved successfully!")
        
        # Get the community ID
        community_id = community_info.json()['community_view']['community']['id']
    
        #####################################################################################
        #####################################################################################

        # # Example: Create a new post in the 'materialdesign' community
        # new_post_response = lemmy.create_post(
        #     community_id=community_id,
        #     name="Test Post Title",
        #     body="This is the body of the test post.",
        #     nsfw=False  # Set to True if the post is NSFW
        # )

        # # Check response for post creation
        # if new_post_response.status_code == 200:
        #     post_data = new_post_response.json()
        #     print(f"Post created successfully! You can view it here: {post_data['post_view']['post']['ap_id']}")
        # else:
        #     print("Failed to create post. Status code:", new_post_response.status_code)
        #     print("Response content:", new_post_response.json())

        #####################################################################################
        #####################################################################################
            
        # # Get the community ID
        # community_id = community_info.json()['community_view']['community']['id']

        # # Fetch posts using the community ID
        # posts_response = lemmy.get_posts(community_id=community_id)

        # # Check and print the posts info in a readable format
        # if posts_response.status_code == 200:
        #     print("\nPosts in 'materialdesign' Community:")
        #     posts_data = posts_response.json().get("posts", [])
        #     for i, post in enumerate(posts_data, start=1):
        #         print(f"\nPost {i}:")
        #         print(json.dumps(post, indent=4))  # Pretty print each post
        # else:
        #     print("Failed to retrieve posts. Status code:", posts_response.status_code)

        ####################################################################################
        ####################################################################################

        # # Attempt to create a comment on the newly created post
        # comment_response = lemmy.create_comment(
        #     content="This is a test comment on the post.",
        #     post_id=post_id,  # post_id is retrieved from the created post's response
        # )

        # # Check response for comment creation
        # if comment_response.status_code == 200:
        #     print("Comment created successfully!")
        # else:
        #     print("Failed to create comment. Status code:", comment_response.status_code)
        #     print("Response content:", comment_response.json())


        ####################################################################################
        ####################################################################################

        # # Attempt to fetch comments for the created post
        # comments_response = lemmy.get_comments(post_id=post_id)  # Assuming `post_id` is from the post you created

        # # Check and print the comments for the post
        # if comments_response.status_code == 200:
        #     print("Comments for the Post:")
        #     comments_data = comments_response.json().get("comments", [])
        #     for i, comment in enumerate(comments_data, start=1):
        #         print(f"\nComment {i}:")
        #         print(json.dumps(comment, indent=4))  # Pretty print each comment
        # else:
        #     print("Failed to retrieve comments. Status code:", comments_response.status_code)
        #     print("Response content:", comments_response.json())

        ####################################################################################
        ####################################################################################

        # # Fetch current subscription status
        # community_info = lemmy.get_community(name="materialdesign")
        # current_status = community_info.json()['community_view']['subscribed']

        # # Determine the desired action based on current status
        # if current_status == "Subscribed":
        #     follow_action = False  # Unsubscribe if currently subscribed
        #     action_text = "unsubscribe"
        # else:
        #     follow_action = True  # Subscribe if currently unsubscribed
        #     action_text = "subscribe"

        # # Attempt to follow or unfollow the community
        # subscribe_response = lemmy.follow_community(community_id=community_id, follow=follow_action)

        # # Check the response and print the correct message
        # if subscribe_response.status_code == 200:
        #     # Confirm action based on the result in the response
        #     subscription_status = subscribe_response.json()['community_view']['subscribed']
        #     if subscription_status == "Subscribed":
        #         print("Successfully subscribed to the community!")
        #     else:
        #         print("Successfully unsubscribed from the community!")
        # else:
        #     print(f"Failed to {action_text}. Status code:", subscribe_response.status_code)
        #     print("Response content:", subscribe_response.json())

        ####################################################################################
        ####################################################################################

        # # Fetch the post to check current voting status
        # post_info = lemmy.get_post(id=post_id)

        # if post_info.status_code == 200:
        #     # Retrieve current vote status
        #     current_vote = post_info.json().get("post_view", {}).get("my_vote", 0)
            
        #     # Determine the opposite action based on current vote status
        #     if current_vote == 1:
        #         # Currently upvoted, so we will remove the vote
        #         vote_score = 0
        #         action_text = "removed vote"
        #     else:
        #         # Currently not upvoted, so we will upvote
        #         vote_score = 1
        #         action_text = "upvoted"

        #     # Attempt to perform the vote action
        #     vote_response = lemmy.like_post(post_id=post_id, score=vote_score)

        #     # Check response for vote action
        #     if vote_response.status_code == 200:
        #         print(f"Successfully {action_text} on the post. Full response content:")
        #         print(json.dumps(vote_response.json(), indent=4))
        #     else:
        #         print(f"Failed to {action_text}. Status code:", vote_response.status_code)
        #         print("Response content:", vote_response.json())
        # else:
        #     print("Failed to retrieve post info for voting status. Status code:", post_info.status_code)
        #     print("Response content:", post_info.json())

        ####################################################################################
        ####################################################################################

        # # Fetch comments for the post to get a comment ID
        # comments_response = lemmy.get_comments(post_id=post_id)

        # # Check response and proceed if comments were fetched successfully
        # if comments_response.status_code == 200:
        #     # Assuming we use the first comment in the list
        #     comments_data = comments_response.json().get("comments", [])
        #     if comments_data:
        #         comment_id = comments_data[0].get("comment", {}).get("id")

        #         # Retrieve the current vote status for this comment
        #         current_vote = comments_data[0].get("my_vote", 0)

        #         # Determine action based on current vote status
        #         if current_vote == 1:
        #             # Currently upvoted, so we will remove the vote
        #             vote_score = 0
        #             action_text = "removed vote on"
        #         else:
        #             # Currently not upvoted, so we will upvote
        #             vote_score = 1
        #             action_text = "upvoted"

        #         # Attempt to vote on the comment
        #         vote_response = lemmy.like_comment(comment_id=comment_id, score=vote_score)

        #         # Check response for vote action on the comment
        #         if vote_response.status_code == 200:
        #             print(f"Successfully {action_text} comment. Full response content:")
        #             print(json.dumps(vote_response.json(), indent=4))
        #         else:
        #             print(f"Failed to {action_text} comment. Status code:", vote_response.status_code)
        #             print("Response content:", vote_response.json())
        #     else:
        #         print("No comments found on the post to vote on.")
        # else:
        #     print("Failed to retrieve comments. Status code:", comments_response.status_code)
        #     print("Response content:", comments_response.json())

        ####################################################################################
        ####################################################################################

        #     # Attempt to fetch the user profile
        # user_profile_response = lemmy.get_person_details(username="staythepath")  # Replace with your username if needed

        # # Check response for profile retrieval
        # if user_profile_response.status_code == 200:
        #     print("User profile retrieved successfully!")
        #     print(json.dumps(user_profile_response.json(), indent=4))  # Pretty print the user profile data
        # else:
        #     print("Failed to retrieve user profile. Status code:", user_profile_response.status_code)
        #     print("Response content:", user_profile_response.json())

        ####################################################################################
        ####################################################################################

        # Attempt to fetch the list of subscribed communities
        subscribed_communities_response = lemmy.get_communities(type_="Subscribed")

        # Check response for subscribed communities
        if subscribed_communities_response.status_code == 200:
            print("Subscribed communities retrieved successfully!")
            subscribed_communities = subscribed_communities_response.json().get("communities", [])
            for i, community in enumerate(subscribed_communities, start=1):
                print(f"\nCommunity {i}:")
                print(json.dumps(community, indent=4))  # Pretty print each community
        else:
            print("Failed to retrieve subscribed communities. Status code:", subscribed_communities_response.status_code)
            print("Response content:", subscribed_communities_response.json())

        ####################################################################################
        ####################################################################################












    else:
        print("Failed to retrieve community info. Status code:", community_info.status_code)
else:
    print("Login failed.")
