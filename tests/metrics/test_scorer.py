import numpy as np
import pytest

from functools import reduce
from operator import mul
from gym import spaces

from d3rlpy.metrics.scorer import td_error_scorer
from d3rlpy.metrics.scorer import discounted_sum_of_advantage_scorer
from d3rlpy.metrics.scorer import average_value_estimation_scorer
from d3rlpy.metrics.scorer import value_estimation_std_scorer
from d3rlpy.metrics.scorer import continuous_action_diff_scorer
from d3rlpy.metrics.scorer import discrete_action_match_scorer
from d3rlpy.metrics.scorer import evaluate_on_environment
from d3rlpy.metrics.scorer import dynamics_observation_prediction_error_scorer
from d3rlpy.metrics.scorer import dynamics_reward_prediction_error_scorer
from d3rlpy.metrics.scorer import dynamics_prediction_variance_scorer
from d3rlpy.metrics.scorer import ope_reward_prediction_error_scorer
from d3rlpy.dataset import Episode, TransitionMiniBatch


# dummy algorithm with deterministic outputs
class DummyAlgo:
    def __init__(self, A, gamma, discrete=False):
        self.A = A
        self.gamma = gamma
        self.discrete = discrete
        self.n_frames = 1

    def predict(self, x):
        x = np.array(x)
        y = np.matmul(x.reshape(x.shape[0], -1), self.A)
        if self.discrete:
            return y.argmax(axis=1)
        return y

    def predict_value(self, x, action, with_std=False):
        values = np.mean(x, axis=1) + np.mean(action, axis=1)
        if with_std:
            return values.reshape(-1), values.reshape(-1) + 0.1
        return values.reshape(-1)


def ref_td_error_score(predict_value, observations, actions, rewards,
                       next_observations, next_actions, terminals, gamma):
    values = predict_value(observations, actions)
    next_values = predict_value(next_observations, next_actions)
    y = rewards + gamma * next_values * (1.0 - terminals)
    return ((y - values)**2).reshape(-1).tolist()


@pytest.mark.parametrize('observation_shape', [(100, )])
@pytest.mark.parametrize('action_size', [2])
@pytest.mark.parametrize('n_episodes', [100])
@pytest.mark.parametrize('episode_length', [10])
@pytest.mark.parametrize('gamma', [0.99])
def test_td_error_scorer(observation_shape, action_size, n_episodes,
                         episode_length, gamma):
    # projection matrix for deterministic action
    A = np.random.random(observation_shape + (action_size, ))
    episodes = []
    for _ in range(n_episodes):
        observations = np.random.random((episode_length, ) + observation_shape)
        actions = np.matmul(observations, A)
        rewards = np.random.random((episode_length, 1))
        episode = Episode(observation_shape, action_size, observations,
                          actions, rewards)
        episodes.append(episode)

    algo = DummyAlgo(A, gamma)

    ref_errors = []
    for episode in episodes:
        batch = TransitionMiniBatch(episode.transitions)
        ref_error = ref_td_error_score(algo.predict_value, batch.observations,
                                       batch.actions,
                                       batch.next_rewards.reshape(-1),
                                       batch.next_observations,
                                       batch.next_actions,
                                       batch.terminals.reshape(-1), gamma)
        ref_errors += ref_error

    score = td_error_scorer(algo, episodes)
    assert np.allclose(score, -np.mean(ref_errors))


def ref_discounted_sum_of_advantage_score(predict_value, observations,
                                          dataset_actions, policy_actions,
                                          gamma):
    dataset_values = predict_value(observations, dataset_actions)
    policy_values = predict_value(observations, policy_actions)
    advantages = (dataset_values - policy_values).reshape(-1).tolist()
    rets = []
    for i in range(len(advantages)):
        sum_advangage = 0.0
        for j, advantage in enumerate(advantages[i:]):
            sum_advangage += (gamma**j) * advantage
        rets.append(sum_advangage)
    return rets


@pytest.mark.parametrize('observation_shape', [(100, )])
@pytest.mark.parametrize('action_size', [2])
@pytest.mark.parametrize('n_episodes', [100])
@pytest.mark.parametrize('episode_length', [10])
@pytest.mark.parametrize('gamma', [0.99])
def test_discounted_sum_of_advantage_scorer(observation_shape, action_size,
                                            n_episodes, episode_length, gamma):
    # projection matrix for deterministic action
    A = np.random.random(observation_shape + (action_size, ))
    episodes = []
    for _ in range(n_episodes):
        observations = np.random.random((episode_length, ) + observation_shape)
        # make difference between algorithm outputs and dataset
        noise = 100 * np.random.random((episode_length, action_size))
        actions = np.matmul(observations, A) + noise
        rewards = np.random.random((episode_length, 1))
        episode = Episode(observation_shape, action_size, observations,
                          actions, rewards)
        episodes.append(episode)

    algo = DummyAlgo(A, gamma)

    ref_sums = []
    for episode in episodes:
        batch = TransitionMiniBatch(episode.transitions)
        policy_actions = algo.predict(batch.observations)
        ref_sum = ref_discounted_sum_of_advantage_score(
            algo.predict_value, batch.observations, batch.actions,
            policy_actions, gamma)
        ref_sums += ref_sum

    score = discounted_sum_of_advantage_scorer(algo, episodes)
    assert np.allclose(score, -np.mean(ref_sums))


@pytest.mark.parametrize('observation_shape', [(100, )])
@pytest.mark.parametrize('action_size', [2])
@pytest.mark.parametrize('n_episodes', [100])
@pytest.mark.parametrize('episode_length', [10])
def test_average_value_estimation_scorer(observation_shape, action_size,
                                         n_episodes, episode_length):
    # projection matrix for deterministic action
    A = np.random.random(observation_shape + (action_size, ))
    episodes = []
    for _ in range(n_episodes):
        observations = np.random.random((episode_length, ) + observation_shape)
        actions = np.matmul(observations, A)
        rewards = np.random.random((episode_length, 1))
        episode = Episode(observation_shape, action_size, observations,
                          actions, rewards)
        episodes.append(episode)

    algo = DummyAlgo(A, 0.0)

    total_values = []
    for episode in episodes:
        batch = TransitionMiniBatch(episode.transitions)
        policy_actions = algo.predict(batch.observations)
        values = algo.predict_value(batch.observations, policy_actions)
        total_values += values.tolist()

    score = average_value_estimation_scorer(algo, episodes)
    assert np.allclose(score, -np.mean(total_values))


@pytest.mark.parametrize('observation_shape', [(100, )])
@pytest.mark.parametrize('action_size', [2])
@pytest.mark.parametrize('n_episodes', [100])
@pytest.mark.parametrize('episode_length', [10])
def test_value_estimation_std_scorer(observation_shape, action_size,
                                     n_episodes, episode_length):
    # projection matrix for deterministic action
    A = np.random.random(observation_shape + (action_size, ))
    episodes = []
    for _ in range(n_episodes):
        observations = np.random.random((episode_length, ) + observation_shape)
        actions = np.matmul(observations, A)
        rewards = np.random.random((episode_length, 1))
        episode = Episode(observation_shape, action_size, observations,
                          actions, rewards)
        episodes.append(episode)

    algo = DummyAlgo(A, 0.0)

    total_stds = []
    for episode in episodes:
        batch = TransitionMiniBatch(episode.transitions)
        policy_actions = algo.predict(batch.observations)
        _, stds = algo.predict_value(batch.observations, policy_actions, True)
        total_stds += stds.tolist()

    score = value_estimation_std_scorer(algo, episodes)
    assert np.allclose(score, -np.mean(total_stds))


@pytest.mark.parametrize('observation_shape', [(100, )])
@pytest.mark.parametrize('action_size', [2])
@pytest.mark.parametrize('n_episodes', [100])
@pytest.mark.parametrize('episode_length', [10])
def test_continuous_action_diff_scorer(observation_shape, action_size,
                                       n_episodes, episode_length):
    # projection matrix for deterministic action
    A = np.random.random(observation_shape + (action_size, ))
    episodes = []
    for _ in range(n_episodes):
        observations = np.random.random((episode_length, ) + observation_shape)
        actions = np.matmul(observations, A)
        actions = np.random.random((episode_length, action_size))
        rewards = np.random.random((episode_length, 1))
        episode = Episode(observation_shape, action_size, observations,
                          actions, rewards)
        episodes.append(episode)

    algo = DummyAlgo(A, 0.0)

    total_diffs = []
    for episode in episodes:
        batch = TransitionMiniBatch(episode.transitions)
        policy_actions = algo.predict(batch.observations)
        diff = ((batch.actions - policy_actions)**2).sum(axis=1).tolist()
        total_diffs += diff
    score = continuous_action_diff_scorer(algo, episodes)
    assert np.allclose(score, -np.mean(total_diffs))


@pytest.mark.parametrize('observation_shape', [(100, )])
@pytest.mark.parametrize('action_size', [2])
@pytest.mark.parametrize('n_episodes', [100])
@pytest.mark.parametrize('episode_length', [10])
def test_discrete_action_math_scorer(observation_shape, action_size,
                                     n_episodes, episode_length):
    # projection matrix for deterministic action
    A = np.random.random(observation_shape + (action_size, ))
    episodes = []
    for _ in range(n_episodes):
        observations = np.random.random((episode_length, ) + observation_shape)
        actions = np.random.randint(action_size, size=episode_length)
        rewards = np.random.random((episode_length, 1))
        episode = Episode(observation_shape, action_size, observations,
                          actions, rewards)
        episodes.append(episode)

    algo = DummyAlgo(A, 0.0, discrete=True)

    total_matches = []
    for episode in episodes:
        batch = TransitionMiniBatch(episode.transitions)
        policy_actions = algo.predict(batch.observations)
        match = (batch.actions.reshape(-1) == policy_actions).tolist()
        total_matches += match
    score = discrete_action_match_scorer(algo, episodes)
    assert np.allclose(score, np.mean(total_matches))


@pytest.mark.parametrize('observation_shape', [(100, ), (4, 84, 84)])
@pytest.mark.parametrize('action_size', [2])
@pytest.mark.parametrize('episode_length', [10])
@pytest.mark.parametrize('n_trials', [10])
def test_evaluate_on_environment(observation_shape, action_size,
                                 episode_length, n_trials):
    shape = (n_trials, episode_length + 1) + observation_shape
    if len(observation_shape) == 3:
        observations = np.random.randint(0, 255, size=shape, dtype=np.uint8)
    else:
        observations = np.random.random(shape)

    class DummyEnv:
        def __init__(self):
            self.episode = 0
            self.observation_space = spaces.Box(low=0,
                                                high=255,
                                                shape=observation_shape)

        def step(self, action):
            self.t += 1
            observation = observations[self.episode - 1, self.t]
            reward = np.mean(observation) + np.mean(action)
            done = self.t == episode_length
            return observation, reward, done, {}

        def reset(self):
            self.t = 0
            self.episode += 1
            return observations[self.episode - 1, 0]

    # projection matrix for deterministic action
    feature_size = reduce(mul, observation_shape)
    A = np.random.random((feature_size, action_size))
    algo = DummyAlgo(A, 0.0)

    ref_rewards = []
    for i in range(n_trials):
        episode_obs = observations[i].reshape((-1, feature_size))
        actions = algo.predict(episode_obs[:-1])
        rewards = np.mean(episode_obs[1:], axis=1) + np.mean(actions, axis=1)
        ref_rewards.append(np.sum(rewards))

    mean_reward = evaluate_on_environment(DummyEnv(), n_trials)(algo)
    assert np.allclose(mean_reward, np.mean(ref_rewards))


class DummyDynamics:
    def __init__(self, noise):
        self.noise = np.reshape(noise, (1, -1))
        self.n_frames = 1

    def predict(self, x, action, with_variance=False):
        y = x + self.noise + np.sum(action)
        reward = np.sum(x, axis=1).reshape((-1, 1))
        if with_variance:
            return y, reward, y.mean(axis=1, keepdims=True)
        return y, reward


@pytest.mark.parametrize('observation_shape', [(100, )])
@pytest.mark.parametrize('action_size', [2])
@pytest.mark.parametrize('n_episodes', [100])
@pytest.mark.parametrize('episode_length', [10])
def test_dynamics_observation_prediction_error_scorer(observation_shape,
                                                      action_size, n_episodes,
                                                      episode_length):
    episodes = []
    for _ in range(n_episodes):
        observations = np.random.random((episode_length, ) + observation_shape)
        actions = np.random.random((episode_length, action_size))
        rewards = np.random.random((episode_length, 1))
        episode = Episode(observation_shape, action_size, observations,
                          actions, rewards)
        episodes.append(episode)

    dynamics = DummyDynamics(np.random.random(observation_shape))

    total_errors = []
    for episode in episodes:
        batch = TransitionMiniBatch(episode.transitions)
        pred_x, _ = dynamics.predict(batch.observations, batch.actions)
        errors = ((batch.next_observations - pred_x)**2).sum(axis=1)
        total_errors += errors.tolist()
    score = dynamics_observation_prediction_error_scorer(dynamics, episodes)
    assert np.allclose(score, -np.mean(total_errors))


@pytest.mark.parametrize('observation_shape', [(100, )])
@pytest.mark.parametrize('action_size', [2])
@pytest.mark.parametrize('n_episodes', [100])
@pytest.mark.parametrize('episode_length', [10])
def test_dynamics_reward_prediction_error_scorer(observation_shape,
                                                 action_size, n_episodes,
                                                 episode_length):
    episodes = []
    for _ in range(n_episodes):
        observations = np.random.random((episode_length, ) + observation_shape)
        actions = np.random.random((episode_length, action_size))
        rewards = np.random.random((episode_length, 1))
        episode = Episode(observation_shape, action_size, observations,
                          actions, rewards)
        episodes.append(episode)

    dynamics = DummyDynamics(np.random.random(observation_shape))

    total_errors = []
    for episode in episodes:
        batch = TransitionMiniBatch(episode.transitions)
        _, pred_reward = dynamics.predict(batch.observations, batch.actions)
        errors = ((batch.next_rewards - pred_reward)**2).reshape(-1)
        total_errors += errors.tolist()
    score = dynamics_reward_prediction_error_scorer(dynamics, episodes)
    assert np.allclose(score, -np.mean(total_errors))


@pytest.mark.parametrize('observation_shape', [(100, )])
@pytest.mark.parametrize('action_size', [2])
@pytest.mark.parametrize('n_episodes', [100])
@pytest.mark.parametrize('episode_length', [10])
def test_dynamics_prediction_variance_scorer(observation_shape, action_size,
                                             n_episodes, episode_length):
    episodes = []
    for _ in range(n_episodes):
        observations = np.random.random((episode_length, ) + observation_shape)
        actions = np.random.random((episode_length, action_size))
        rewards = np.random.random((episode_length, 1))
        episode = Episode(observation_shape, action_size, observations,
                          actions, rewards)
        episodes.append(episode)

    dynamics = DummyDynamics(np.random.random(observation_shape))

    total_variances = []
    for episode in episodes:
        batch = TransitionMiniBatch(episode.transitions)
        _, _, var = dynamics.predict(batch.observations, batch.actions, True)
        total_variances += var.tolist()
    score = dynamics_prediction_variance_scorer(dynamics, episodes)
    assert np.allclose(score, -np.mean(total_variances))


class DummyOPE:
    def __init__(self):
        self.n_frames = 1

    def predict(self, x, action):
        reward = np.sum(x, axis=1).reshape((-1, 1))
        log_prob = np.mean(x, axis=1).reshape((-1, 1))
        return reward, log_prob


@pytest.mark.parametrize('observation_shape', [(100, )])
@pytest.mark.parametrize('action_size', [2])
@pytest.mark.parametrize('n_episodes', [100])
@pytest.mark.parametrize('episode_length', [10])
def test_ope_reward_prediction_error_scorer(observation_shape, action_size,
                                            n_episodes, episode_length):
    episodes = []
    for _ in range(n_episodes):
        observations = np.random.random((episode_length, ) + observation_shape)
        actions = np.random.random((episode_length, action_size))
        rewards = np.random.random((episode_length, 1))
        episode = Episode(observation_shape, action_size, observations,
                          actions, rewards)
        episodes.append(episode)

    ope = DummyOPE()

    total_errors = []
    for episode in episodes:
        batch = TransitionMiniBatch(episode.transitions)
        pred_reward, _ = ope.predict(batch.observations, batch.actions)
        errors = ((batch.next_rewards - pred_reward)**2).reshape(-1)
        total_errors += errors.tolist()
    score = ope_reward_prediction_error_scorer(ope, episodes)
    assert np.allclose(score, -np.mean(total_errors))
